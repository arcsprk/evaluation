import requests
import json
import os
from dotenv import load_dotenv

from langfuse.decorators import observe, langfuse_context


from langfuse import Langfuse
 
 
load_dotenv()


# Create Langfuse client
langfuse = Langfuse()

TRACE_NAME = "spark"

def get_stream_chunks(api_url: str, headers: dict = None, payload: dict = None):
    """
    Retrieve stream chunks from an API response.
    
    Args:
        api_url (str): The API endpoint URL
        headers (dict, optional): HTTP headers for the request
        payload (dict, optional): Request payload/body
    
    Yields:
        dict: Individual stream chunks
    """

    # Use streaming mode with requests library
    with requests.post(api_url,
                        headers=headers, 
                        json=payload,
                        # data=json.dumps(data), 
                        stream=True) as response:        
        response.raise_for_status() # Ensure successful response

        response_text = response.text
        try:
            data = json.loads(response_text)
            # print(data)
            yield data
        except json.JSONDecodeError:
            print(f"Could not parse response: {response_text}")




        # # Iterate through response lines
        # for line in response.iter_lines():
        #     print(f"*** Raw line: {line}", flush=True)
        #     if line:
        #         # Decode byte string and parse JSON
        #         try:
        #             chunk = json.loads(line.decode('utf-8'))
        #             yield chunk
        #         except json.JSONDecodeError:
        #             print(f"Could not parse chunk: {line}")

# @observe()
def get_chat_completion_stream(api_url: str, api_key: str, model: str, messages: list, model_params: dict):
    """
    Calls the OpenAI Chat Completion API.
    Args:
        api_key: Your OpenAI API key.  It is highly recommended to pass this
                 as an environment variable rather than hardcoding it.
        model: The name of the model to use (e.g., "gpt-4o").
        messages: A list of message objects, where each object has "role" and "content" keys.
    Returns:
        A dictionary containing the API response, or None if there was an error.
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": messages,
        **model_params
    }

    # langfuse_context.update_current_observation(
    #     input=messages,
    #     model=model,
    #     metadata=model_params,        
    # )

    generation = langfuse.generation(
        name=TRACE_NAME + "-" + model,
        model=model,
        # model_parameters=model_params,
        input=messages,
        # metadata={"stream": True}
        metadata={"stream": True, "model": model, "parameters": model_params}
    )


    for chunk in get_stream_chunks(api_url, headers, payload):
        # langfuse_context.update_current_observation(
        #     usage_details=chunk["usage"]
        #     # usage_details={
        #     #     "input": chunk["usage"][],
        #     #     "output": chunk.usage.output_tokens
        #     # }
        # )
        # Update span and sets end_time
        # generation.end(output=chunk)
        generation.end(
            output=chunk["choices"][0]["message"]["content"],
            metadata={"model": chunk["model"], "finish_reason": chunk["choices"][0]["finish_reason"], "usage": chunk["usage"]})
        langfuse.flush()            
        return chunk

    # langfuse_context.flush()


# @observe()
def get_chat_completion(api_url: str, api_key: str, model: str, messages: list, model_params: dict) -> dict:
    """
    Calls the OpenAI Chat Completion API.
    Args:
        api_key: Your OpenAI API key.  It is highly recommended to pass this
                 as an environment variable rather than hardcoding it.
        model: The name of the model to use (e.g., "gpt-4o").
        messages: A list of message objects, where each object has "role" and "content" keys.
    Returns:
        A dictionary containing the API response, or None if there was an error.
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    # data = {
    #     "model": model,
    #     "messages": messages,
    #     **model_params
    # }

    payload = {
        "model": model,
        "messages": messages,
        **model_params
    }
    try:
        # response = requests.post(api_url, headers=headers, data=json.dumps(data))
        generation = langfuse.generation(
            name=TRACE_NAME + "-" + model,
            model=model,
            # model_parameters=model_params,
            input=messages,
            # metadata={"stream": False}
            metadata={"stream": False, "model": model, "parameters": model_params}
        )

        with requests.post(api_url, 
                    headers=headers,
                    json=payload,
                    # data=json.dumps(data), 
                    stream=False) as response:
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            # langfuse_context.update_current_observation(
            #     usage_details={
            #         "input": response.usage.input_tokens,
            #         "output": response.usage.output_tokens
            #     }
            # )
                    # Update span and sets end_time
        # generation.end(output=chunk)
            generation.end(
                output=response.json()["choices"][0]["message"]["content"],
                # output=response,
                metadata={
                    "model": response.json()["model"],
                    "finish_reason": response.json()["choices"][0]["finish_reason"],
                    "usage": response.json()["usage"],
                    }
                )
            langfuse.flush()               
            return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling API: {e}")
        return None



if __name__ == '__main__':
    # Get the API key from an environment variable.  This is best practice.
    api_url = "https://api.openai.com/v1/chat/completions"  # OPENAI_API_URL
    model_api_key = os.environ.get("OPENAI_API_KEY")

    # api_url = "https://api.groq.com/openai/v1/chat/completions" # GROQ_API_URL
    # model_api_key = os.environ.get("GROQ_API_KEY")

    # model_name = "gpt-4o"
    model_name = "o3-mini"
    
    # model_name = "deepseek-r1-distill-qwen-32b"

    # model_params = {}
    model_params = {
        "response_format": {
            "type": "text"
        },
        "reasoning_effort": "medium",
    }
    # model_params = {
    #     "temperature": 0.7,
    #     "max_completion_tokens": 1024,
    #     "top_p": 0.95,
    #     # stop=None,
    # }    
    # model_params = dict(
    #     temperature=0.7,
    #     max_completion_tokens=1024,
    #     top_p=0.95,
    #     stop=None,
    # )

    # OpenAI
    # "o1"
    # "o3-mini"
    # "gpt-4.5-preview"
    # "gpt-4o"
    # "gpt-4o-mini"

    # ## Groq models

    # # Alibaba Cloud
    # "qwen-2.5-32b"
    # "qwen-2.5-coder-32b"
    # "qwen-qwq-32b"

    # # DeepSeek / Alibaba Cloud
    # "deepseek-r1-distill-qwen-32b"

    # # DeepSeek / Meta
    # "deepseek-r1-distill-llama-70b"

    # # Google
    # "gemma2-9b-it"

    # # Meta
    # "llama3-70b-8192"
    # "llama3-8b-8192"
    # "llama-guard-3-8b"

    # # Mistral AI
    # "mistral-saba-24b"


    if not model_api_key:
        print("Error: API key not found.  Please set the API Key environment variable.")
        exit(1)


    # user_input = """
    # ```def f(s, x):
    #     count = 0
    #     while s[:len(x)] == x and count < len(s)-len(x):
    #     s = s[len(x):]
    #     count += len(x)
    #     return s```
    # what is the output for the function f('If you want to live a happy life! Daniel', 'Daniel')?
    # """

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

    STREAM = True

    # Create generation in Langfuse
    # generation = langfuse.generation(
    #     name="test-tracing",
    #     model=model_name,
    #     model_parameters=model_params,
    #     input=messages,
    #     metadata={"stream": STREAM}
    # )


    if STREAM == True:
        chat_response = get_chat_completion_stream(api_url, model_api_key, model_name, messages, model_params)
        print(f"Chat response (stream) ({type(chat_response)}):\n {json.dumps(chat_response, indent=2, ensure_ascii=False)}")


    else:
        # Example usage:
        chat_response= get_chat_completion(api_url, model_api_key, model_name, messages, model_params)

        if chat_response:
            # print(json.dumps(chat_response, indent=2, ensure_ascii=False)) # Nicely formatted output
            print(f"Chat response ({type(chat_response)}):\n {json.dumps(chat_response, indent=2, ensure_ascii=False)}")
        else:
            print("Failed to get a response from the model API.")

    # Update span and sets end_time
    # generation.end(output=chat_response)
    # generation.end(output=chat_response["choices"][0]["message"]["content"])
    # langfuse.flush()

    # output example
    # {
    #     "id": "chatcmpl-BEg89ehxWb3fz9hTgNPzybmquZ9fP",
    #     "object": "chat.completion",
    #     "created": 1742838241,
    #     "model": "o3-mini-2025-01-31",
    #     "choices": [
    #         {
    #         "index": 0,
    #         "message": {
    #             "role": "assistant",
    #             "content": "We notice that each of the 5 groups of letters consists of three letters that follow specific, orderly progressions:\n\n1. First letters:\n  S, T, U, __, W  → each letter increases by 1 (S, T, U, then V, then W).\n\n2. Second letters:\n  C, E, G, __, K  → each letter increases by 2 (C, then E, then G, then I, then K).\n\n3. Third letters:\n  D, F, H, __, L  → each letter increases by 2 (D, then F, then H, then J, then L).\n\nThus, for the missing fourth group, the letters should be:\n  First letter: V\n  Second letter: I\n  Third letter: J\n\nSo the missing group is VIJ. \n\nAmong the provided choices, VIJ is the correct answer.",
    #             "refusal": null,
    #             "annotations": []
    #         },
    #         "finish_reason": "stop"
    #         }
    #     ],
    #     "usage": {
    #         "prompt_tokens": 49,
    #         "completion_tokens": 1044,
    #         "total_tokens": 1093,
    #         "prompt_tokens_details": {
    #         "cached_tokens": 0,
    #         "audio_tokens": 0
    #         },
    #         "completion_tokens_details": {
    #         "reasoning_tokens": 832,
    #         "audio_tokens": 0,
    #         "accepted_prediction_tokens": 0,
    #         "rejected_prediction_tokens": 0
    #         }
    #     },
    #     "service_tier": "default",
    #     "system_fingerprint": "fp_42bfad963b"