import asyncio
import aiohttp
import time

async def send_request_with_timeout(sem, session, api_url, model_api_key, model_name, messages, model_params, timeout):
    """
    Sends a streaming request to the API asynchronously with concurrency control.
    Returns the response content and status ('complete' or 'incomplete').
    """
    full_response = ""
    completion_status = "incomplete"

    async with sem:  # Semaphore로 동시 실행 제한
        try:
            start_time = time.time()  # 요청 시작 시간 기록

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
                async for line in response.content:
                    decoded_line = line.decode("utf-8").strip()

                    # [DONE] 감지
                    if decoded_line == "[DONE]":
                        completion_status = "complete"
                        break

                    # JSON 데이터 파싱 및 delta.content 추출
                    if decoded_line.startswith("data:"):
                        try:
                            json_data = json.loads(decoded_line.lstrip("data:").strip())
                            content = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                full_response += content  # 응답 누적 저장
                                print(content, end="")  # 실시간 출력
                        except json.JSONDecodeError as e:
                            print(f"Error parsing JSON: {e}")
                            print(f"Problematic data: {decoded_line}")

                    # 경과 시간 확인
                    elapsed_time = time.time() - start_time
                    if elapsed_time > timeout:
                        print("\nRequest exceeded timeout limit.")
                        completion_status = "incomplete"
                        break

        except asyncio.TimeoutError:
            print("\nTimeout occurred during the request.")

    return full_response, completion_status


async def parallel_requests(api_url, model_api_key, model_name, messages_list, model_params, timeout, max_concurrent_requests):
    """
    Executes multiple requests in parallel with a limit on concurrency.
    """
    sem = asyncio.Semaphore(max_concurrent_requests)  # 동시 실행 제한 설정
    async with aiohttp.ClientSession() as session:
        tasks = [
            send_request_with_timeout(sem, session, api_url, model_api_key, model_name, messages, model_params, timeout)
            for messages in messages_list
        ]
        results = await asyncio.gather(*tasks)  # 병렬로 모든 요청 실행
        return results


# 실행 예시
async def main():
    api_url = "https://api.openai.com/v1/chat/completions"
    model_api_key = "YOUR_API_KEY"
    model_name = "gpt-4o"
    messages_list = [
        [{"role": "user", "content": "Message 1"}],
        [{"role": "user", "content": "Message 2"}],
        [{"role": "user", "content": "Message 3"}],
        [{"role": "user", "content": "Message 4"}],
        [{"role": "user", "content": "Message 5"}]
    ]
    model_params = {}
    timeout = 10  # 타임아웃 설정 (초 단위)
    max_concurrent_requests = 2  # 최대 동시 실행 요청 수

    responses = await parallel_requests(api_url, model_api_key, model_name, messages_list, model_params, timeout, max_concurrent_requests)
    
    for i, (response_content, status) in enumerate(responses):
        print(f"\nResponse {i+1}:")
        print(response_content)
        print(f"Status: {status}")

# asyncio 실행
asyncio.run(main())
