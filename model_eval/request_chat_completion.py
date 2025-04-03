import requests
import os
import json
import time
from dotenv import load_dotenv

load_dotenv()


def deep_get(dictionary, keys, default=None):
    """
    Safely get a nested value from a dictionary.
    Args:
        dictionary (dict): The dictionary to search.
        keys (list): A list of keys representing the path to the desired value.
        default: The default value to return if any key is missing.
    Returns:
        The value at the nested key path or the default value.
    """
    for key in keys:
        if isinstance(dictionary, dict):
            dictionary = dictionary.get(key, default)
        else:
            return default
    return dictionary




def request_chat_completion(api_url, model_api_key, model_name, messages, model_params={}, stream=True, timeout=60):
 

    # 스트리밍된 응답을 저장할 변수
    full_response = ""
    completion_status = "incomplete"  # 초기 상태는 incomplete로 설정

    try:

        start_time = time.time()

        # API 요청 설정
        response = requests.post(
            api_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {model_api_key}"
            },
            json={
                "model": model_name,
                "messages": messages,
                **model_params,
                "stream": stream  # completion streaming
            },
            stream=stream,  # SSE streaming
        )

        
        # 응답 스트림 처리
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode("utf-8").strip()
                

                # JSON 데이터 파싱 및 delta.content 추출
                if decoded_line.startswith("data:"):
                    try:
                        # [DONE] 감지
                        if "[DONE]" in decoded_line:
                            completion_status = "complete"

                            print(f"\n\nElapsed time until completed: {time.time() - start_time:.2f} seconds", end="")  # 실시간 출력
                            break
                        
                        # 'data:'와 공백 제거 후 JSON 파싱
                        json_data = json.loads(decoded_line.lstrip("data:").strip())
                        content = json_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            full_response += content  # content를 누적 저장
                            print(content, end="")  # 실시간 출력
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON: {e}")
                        print(f"Problematic data: {decoded_line}")

            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                print("\nRequest exceeded timeout limit.")
                completion_status = "incomplete"
                break
                              

    except requests.exceptions.Timeout:
        print("\nTimeout occurred. Streaming stopped.")

    print(f"\n\nElapsed time until response finished: {time.time() - start_time:.2f} seconds")

    return full_response, completion_status


if __name__ == "__main__":

    api_url = "https://api.openai.com/v1/chat/completions"  # OPENAI_API_URL
    model_api_key = os.environ.get("OPENAI_API_KEY")
    model_name = "gpt-4o"
    model_params = {
        "temperature": 0.7,
        "max_tokens": 1024,
        "top_p": 0.95,
        "stop": None,
    }

    user_input = """
    SCD, TEF, UGH, ____, WKL

    IJT
    VIJ
    CMN
    UJI
    빈칸에 들어갈 값은?
    """


    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": user_input}
    ]
    # 실행 및 결과 저장
    final_response, completion_status = request_chat_completion(api_url, model_api_key, model_name, messages, model_params, stream=True, timeout=2)
    print("\nFull Response:\n", final_response)

    print("\nCompletion Status:", completion_status)