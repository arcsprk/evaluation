import os
import json
import asyncio
import aiohttp
import time
from dotenv import load_dotenv

load_dotenv()

async def stream_request_with_timeout(sem, session, api_url, model_api_key, model_name, messages, model_params, timeout):
    """
    Sends a streaming request to the API and yields content chunks as they arrive.
    Also collects and yields metadata at the end of streaming.
    """

    metadata = {
        "model": model_name,
        "params": model_params.copy(),
        "usage": None,
        "finish_reason": None
    }
    
    async with sem:  # 세마포어로 동시 실행 제한
        start_time = time.time()  # 요청 시작 시간 기록
        # metadata["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))
        metadata["started_at"] = f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}.{int((start_time % 1) * 1000):03d}"
        try:
            async with session.post(
                api_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {model_api_key}"
                },
                json={
                    "model": model_name,
                    "messages": messages,
                    **model_params,
                    "stream": True  # 스트리밍 활성화
                },
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    current_time = time.time() 
                    elapsed = current_time - start_time
                    yield f"Error: {response.status} - {error_text}", "error", elapsed, metadata
                    return

                async for line in response.content:
                    # 타임아웃 확인
                    current_time = time.time() 
                    elapsed_time = current_time - start_time
                    if elapsed_time > timeout:
                        yield "\nRequest exceeded timeout limit.", "timeout", elapsed_time, metadata
                        return

                    decoded_line = line.decode("utf-8").strip()
                    
                    # data: 접두사 확인
                    if decoded_line.startswith("data:"):
                        data_content = decoded_line.lstrip("data:").strip()
                        
                        # [DONE] 감지
                        if data_content == "[DONE]":
                            current_time = time.time() 
                            final_elapsed = current_time - start_time
                            yield None, "complete", final_elapsed, metadata
                            return
                        
                        try:
                            json_data = json.loads(data_content)
                            delta = json_data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            
                            # 메타데이터 수집
                            finish_reason = json_data.get("choices", [{}])[0].get("finish_reason")
                            if finish_reason:
                                metadata["finish_reason"] = finish_reason
                            
                            # 사용량 데이터 수집 (스트리밍의 마지막에 포함될 수 있음)
                            if "usage" in json_data:
                                metadata["usage"] = json_data["usage"]
                            
                            # 모델 정보 업데이트 (응답에서 제공된 경우)
                            if "model" in json_data:
                                metadata["model"] = json_data["model"]
                            
                            if content:
                                current_elapsed = time.time()  - start_time
                                yield content, "chunk", current_elapsed, metadata
                        except json.JSONDecodeError:
                            continue

        except asyncio.TimeoutError:
            final_elapsed = time.time()  - start_time
            yield "\nTimeout occurred during the request.", "timeout", final_elapsed, metadata
        except Exception as e:
            final_elapsed = time.time()  - start_time
            yield f"\nError during request: {str(e)}", "error", final_elapsed, metadata


async def process_single_request(sem, session, api_url, model_api_key, model_name, messages, model_params, timeout, request_id=None):
    """
    Process a single request and collect all chunks into a full response.
    Returns the full response, final status, elapsed time and metadata.
    """
    full_response = ""
    final_status = "incomplete"
    total_elapsed_time = 0
    first_token_time = None
    final_metadata = None

    request_id = request_id if request_id is not None else id(messages)  # 요청 식별자
    request_start_time = time.time() 
    print(f"[Request {request_id}] Starting at {time.strftime('%H:%M:%S', time.localtime(request_start_time))}")

    # 요청에 대한 메타데이터를 저장할 변수 초기화
    request_metadata = {
        "model": model_name,
        "params": model_params,
        "usage": None
    }

    async for content, status, elapsed, metadata in stream_request_with_timeout(
        sem, session, api_url, model_api_key, model_name, messages, model_params, timeout
    ):
    

        # 메타데이터 업데이트
        if metadata:
            request_metadata.update(metadata)
        
        
        if status == "chunk":
            if not first_token_time and content:
                first_token_time = elapsed
                print(f"[Request {request_id}] First token received after {first_token_time:.4f} seconds")
            
            full_response += content
            # print(f"[Request {request_id}] {content}", end="", flush=True)  # 실시간 출력
            print(f"{content}", end="", flush=True)  # 실시간 출력
        elif status in ("complete", "error", "timeout"):
            final_status = status
            total_elapsed_time = elapsed
            final_metadata = metadata  # 최종 메타데이터 저장
            if content:  # content가 None이 아닐 경우만 출력
                # print(f"[Request {request_id}] {content}", flush=True)
                print(f"{content}", flush=True)


    # 측정 결과 기록
    request_metrics = {
        "request_id": request_id,
        "started_at": request_metadata.get("started_at"),
        "status": final_status,
        "total_elapsed_time": total_elapsed_time,
        "first_token_time": first_token_time,
        "response_length": len(full_response),
        "tokens_per_second": len(full_response) / total_elapsed_time if total_elapsed_time > 0 else 0,
        "metadata": request_metadata
    }
    
    print(f"\n[Request {request_id}] Completed with status: {final_status}")
    print(f"[Request {request_id}] Total time: {total_elapsed_time:.4f} seconds")
    if first_token_time:
        print(f"[Request {request_id}] Time to first token: {first_token_time:.4f} seconds")
        print(f"[Request {request_id}] Generation time: {total_elapsed_time - first_token_time:.4f} seconds")
    
    # 토큰 사용량 정보 출력 (있는 경우)
    usage = request_metadata.get("usage")
    if usage:
        print(f"[Request {request_id}] Token usage: {usage}")
    
    return full_response, final_status, request_metrics


async def parallel_requests(api_url, model_api_key, model_name, messages_list, model_params, timeout, max_concurrent_requests):
    """
    Executes multiple requests in parallel with a limit on concurrency.
    Returns responses and metrics for all requests.
    """
    sem = asyncio.Semaphore(max_concurrent_requests)  # 동시 실행 제한 설정
    async with aiohttp.ClientSession() as session:
        tasks = [
            process_single_request(sem, session, api_url, model_api_key, model_name, messages, model_params, timeout, i)
            for i, messages in enumerate(messages_list)
        ]
        results = await asyncio.gather(*tasks)  # 병렬로 모든 요청 실행
        return results


# 결과를 JSON 파일로 저장하는 함수
def save_results_to_json(results, file_path="./result/api_results.json"):
    # JSON 직렬화 가능한 형태로 결과 변환
    serializable_results = []
    
    for response, status, metrics in results:
        serializable_results.append({
            "response": response,
            "status": status,
            "metrics": {
                "request_id": metrics["request_id"],
                "started_at": metrics["started_at"],
                "status": metrics["status"],
                "total_elapsed_time": metrics["total_elapsed_time"],
                "first_token_time": metrics["first_token_time"],
                "response_length": metrics["response_length"],
                "tokens_per_second": metrics["tokens_per_second"],
                "metadata": metrics["metadata"]
            }
        })
    
    # 파일에 저장
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(serializable_results, f, ensure_ascii=False, indent=2)
    
    print(f"Results saved to {file_path}")


# 실행 예시
async def test_batch_inference():
    api_url = "https://api.openai.com/v1/chat/completions"
    model_api_key = os.getenv("OPENAI_API_KEY")
    if not model_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
        
    model_name = "gpt-4o"
    messages_list = [
        [{"role": "user", "content": "3+5*23?"}],
        [{"role": "user", "content": "reverse the string 'hello'"}],
        [{"role": "user", "content": "Write a short paragraph explaining machine learning"}],
        [{"role": "user", "content": "What are the benefits of async programming in Python?"}],
        [{"role": "user", "content": "Generate a simple Python function to calculate factorial"}]
    ]
    
    # 모델 파라미터 설정 (토큰 사용량 측정에 중요)
    model_params = {
        "temperature": 0.7,
        "max_tokens": 500
    }
    
    timeout = 30  # 타임아웃 설정 (초 단위)
    max_concurrent_requests = 2  # 최대 동시 실행 요청 수

    print(f"Starting {len(messages_list)} requests with max {max_concurrent_requests} concurrent connections")
    test_start_time = time.time() 
    
    responses = await parallel_requests(api_url, model_api_key, model_name, messages_list, model_params, timeout, max_concurrent_requests)
    
    total_time = time.time()  - test_start_time
    print(f"\n--- Summary of All Requests ---\n")
    print(f"Total time for all requests: {total_time:.4f} seconds")
    
    # 성능 메트릭스 요약
    all_metrics = [metrics for _, _, metrics in responses]
    avg_total_time = sum(m["total_elapsed_time"] for m in all_metrics) / len(all_metrics)
    avg_first_token = sum(m["first_token_time"] for m in all_metrics if m["first_token_time"]) / len(all_metrics)
    
    print(f"Average request time: {avg_total_time:.4f} seconds")
    print(f"Average time to first token: {avg_first_token:.4f} seconds")
    
    # 토큰 사용량 요약
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    
    for i, (_, status, metrics) in enumerate(responses):
        print(f"\nRequest {i} - Status: {status}")
        print(f"  Started at: {metrics['metadata']['started_at']}")
        print(f"  Time: {metrics['total_elapsed_time']:.4f}s, First token: {metrics['first_token_time']:.4f}s")
        
        # 토큰 사용량 정보가 있으면 추가
        usage = metrics["metadata"].get("usage")
        if usage:
            print(f"  Tokens: Prompt={usage.get('prompt_tokens', 0)}, "
                  f"Completion={usage.get('completion_tokens', 0)}, "
                  f"Total={usage.get('total_tokens', 0)}")
            
            total_prompt_tokens += usage.get('prompt_tokens', 0)
            total_completion_tokens += usage.get('completion_tokens', 0)
            total_tokens += usage.get('total_tokens', 0)
    
    print(f"\nTotal token usage:")
    print(f"  Prompt tokens: {total_prompt_tokens}")
    print(f"  Completion tokens: {total_completion_tokens}")
    print(f"  Total tokens: {total_tokens}")
    
    # 결과를 JSON 파일로 저장
    save_results_to_json(responses)

# asyncio 실행
if __name__ == "__main__":
    asyncio.run(test_batch_inference())