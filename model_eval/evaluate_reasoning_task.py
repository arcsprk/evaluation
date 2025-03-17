import pandas as pd
import json
from openai import OpenAI

import time
import numpy as np
from dotenv import load_dotenv
import os
# OpenAI API 키 설정
# openai.api_key = "your-api-key"  # 실제 사용 시 API 키를 입력하세요

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def request_answer(question):
    """
    OpenAI API를 호출하여 질문에 대한 답변을 받습니다.
    
    Args:
        question (str): 질문 문자열
        
    Returns:
        tuple: (response_json, answer) - API 응답 JSON과 답변 텍스트
    """
    try:
        # API 호출 (gpt-4 모델 사용)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": question}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        # JSON 응답 저장
        response_str = response.model_dump()

        print(f" type(response_str): {type(response_str)}\n response_str: {response_str}")
        
        # 답변 텍스트 추출
        answer = response.choices[0].message.content
        
        return response_str, answer
    
    except Exception as e:
        print(f"Error in request_answer: {e}")
        return "{}", "Error occurred while processing the request."

def request_answer_score(question, golden_answer, answer):
    """
    OpenAI API를 호출하여 답변의 점수를 계산합니다.
    
    Args:
        question (str): 질문 문자열
        golden_answer (str): 표준 답변
        answer (str): 실제 생성된 답변
        
    Returns:
        float: 답변 점수 (0~1 사이)
    """
    try:
        prompt = f"""
        질문: {question}
        
        표준 답변: {golden_answer}
        
        생성된 답변: {answer}
        
        위 생성된 답변이 표준 답변과 비교하여 얼마나 정확한지 0부터 1 사이의 점수로 평가해주세요.
        점수만 반환해주세요.
        """
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that evaluates answers."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=20
        )
        
        # 점수 추출 (숫자만 추출)
        score_text = response.choices[0].message.content.strip()
        # 숫자 형식으로 변환 (0~1 사이의 실수)
        score = float(score_text)
        
        # 점수가 0~1 범위를 벗어나면 조정
        score = max(0, min(1, score))
        
        return score
    
    except Exception as e:
        print(f"Error in request_answer_score: {e}")
        return 0.0

def process_dataframe(df):
    """
    데이터프레임의 각 행에 대해 답변을 생성하고 점수를 계산합니다.
    
    Args:
        df (pandas.DataFrame): 처리할 데이터프레임
        
    Returns:
        pandas.DataFrame: 처리된 데이터프레임
    """
    # 결과를 저장할 빈 열 생성
    if 'response' not in df.columns:
        df['response'] = ""
    if 'answer' not in df.columns:
        df['answer'] = ""
    if 'score' not in df.columns:
        df['score'] = np.nan
    
    # 각 행 처리
    for idx, row in df.iterrows():
        question = row['question']
        golden_answer = row['golden_answer']
        
        print(f"Processing row {idx+1}/{len(df)}: {question[:50]}...")
        
        # 답변 생성
        response_json, answer = request_answer(question)
        
        # 결과 저장
        df.at[idx, 'response'] = response_json
        df.at[idx, 'answer'] = answer
        
        # 점수 계산
        score = request_answer_score(question, golden_answer, answer)
        df.at[idx, 'score'] = score
        
        print(f"Row {idx+1} - Score: {score:.2f}")
        
        # API 요청 간 간격 두기 (Rate limit 방지)
        time.sleep(1)
    
    return df

# 샘플 사용법
if __name__ == "__main__":
    # 샘플 데이터프레임 생성
    sample_df = pd.DataFrame({
        'question': [
            "파이썬의 주요 특징은 무엇인가요?",
            "인공지능과 머신러닝의 차이점은 무엇인가요?"
        ],
        'golden_answer': [
            "파이썬의 주요 특징은 간결한 문법, 인터프리터 언어, 동적 타이핑, 객체 지향, 풍부한 라이브러리 등이 있습니다.",
            "인공지능은 인간의 지능을 모방하는 넓은 개념이고, 머신러닝은 데이터를 기반으로 학습하는 인공지능의 한 분야입니다."
        ]
    })
    # 데이터프레임 처리
    # processed_df = process_dataframe(sample_df)

    import pandas as pd

    # Login using e.g. `huggingface-cli login` to access this dataset
    df = pd.read_parquet("hf://datasets/nuprl/verbal-reasoning-challenge/data/test-00000-of-00001.parquet")

    df = df.rename(columns={"challenge": "question", "answer": "golden_answer"})
    df["answer"] = ""
    df["score"] = np.nan


    processed_df = process_dataframe(df.iloc[0:10])
    
    # 결과 출력
    print("\n처리 결과:")
    print(processed_df[['question', 'golden_answer', 'answer', 'score']])
    
    # 결과 저장 (선택사항)
    processed_df.to_csv('./result/processed_results.csv', index=False)