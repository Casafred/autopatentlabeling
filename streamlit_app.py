import streamlit as st
import pandas as pd
from io import BytesIO, StringIO
import json
import time
from zhipuai import ZhipuAI

# 页面配置
st.set_page_config(page_title="文本分类分析工具", layout="wide")

# 自定义CSS样式
st.markdown("""
    <style>
    .main {
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }
    .stTextInput>div>div>input {
        background-color: #f0f2f6;
    }
    </style>
""", unsafe_allow_html=True)

def create_batch_jsonl(df, classification_system):
    """创建batch处理所需的jsonl文件内容"""
    jsonl_content = StringIO()
    
    for idx, row in df.iterrows():
        request = {
            "custom_id": f"request-{idx}",
            "method": "POST",
            "url": "/v4/chat/completions",
            "body": {
                "model": "glm-4",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个文本分类专家。"
                    },
                    {
                        "role": "user",
                        "content": f"""
                        请根据以下分类体系对文本进行分类，并说明分类理由：
                        分类体系：{classification_system}
                        
                        文本内容：{row['摘要']}
                        
                        请以JSON格式返回，包含两个字段：
                        1. category: 分类标签
                        2. reason: 分类理由
                        """
                    }
                ],
                "temperature": 0.1
            }
        }
        jsonl_content.write(json.dumps(request, ensure_ascii=False) + '\n')
    
    return jsonl_content.getvalue()

def process_batch_results(content):
    """处理batch处理的结果"""
    results = []
    for line in content.split('\n'):
        if line.strip():
            try:
                result = json.loads(line)
                response_content = json.loads(
                    result['response']['body']['choices'][0]['message']['content'].strip('`json\n')
                )
                results.append(response_content)
            except Exception as e:
                results.append({"error": str(e)})
    return results

def main():
    st.title("文本分类分析工具")
    
    # 创建两个主要区域
    setup_col, upload_col = st.columns(2)
    
    with setup_col:
        st.subheader("1. 设置分类系统")
        
        # ZhipuAI API密钥输入
        api_key = st.text_input("输入智谱AI API密钥", type="password")
        
        # 分类级别设置
        levels = st.number_input("设置分类级别数", min_value=1, max_value=5, value=1)
        
        # 动态创建分类系统输入界面
        classification_system = {}
        for level in range(1, levels + 1):
            st.markdown(f"#### 第{level}级分类")
            
            num_labels = st.number_input(f"第{level}级分类的标签数量", min_value=1, value=1, key=f"num_labels_{level}")
            
            level_labels = {}
            for i in range(num_labels):
                col1, col2 = st.columns(2)
                with col1:
                    label = st.text_input(f"标签 {i+1}", key=f"label_{level}_{i}")
                with col2:
                    description = st.text_input(f"解释 {i+1}", key=f"desc_{level}_{i}")
                if label and description:
                    level_labels[label] = description
            
            classification_system[f"level_{level}"] = level_labels
        
        if st.button("保存分类系统"):
            st.session_state.classification_system = classification_system
            st.success("分类系统已保存！")
    
    with upload_col:
        st.subheader("2. 上传和处理数据")
        
        uploaded_file = st.file_uploader("上传Excel文件", type=['xlsx', 'xls'])
        
        if uploaded_file is not None and api_key:
            try:
                df = pd.read_excel(uploaded_file)
                
                if '摘要' not in df.columns:
                    st.error('上传的Excel文件中没有找到摘要列！')
                    return
                
                st.write("原始数据预览：")
                st.dataframe(df.head())
                
                if st.button("开始处理"):
                    client = ZhipuAI(api_key=api_key)
                    
                    # 创建batch处理文件
                    jsonl_content = create_batch_jsonl(df, classification_system)
                    
                    # 保存为临时文件
                    with open("temp_batch.jsonl", "w", encoding='utf-8') as f:
                        f.write(jsonl_content)
                    
                    # 上传文件
                    with st.spinner("上传文件中..."):
                        result = client.files.create(
                            file=open("temp_batch.jsonl", "rb"),
                            purpose="batch"
                        )
                        file_id = result.id
                    
                    # 创建batch任务
                    with st.spinner("创建批处理任务..."):
                        batch_job = client.batches.create(
                            input_file_id=file_id,
                            endpoint="/v4/chat/completions",
                            auto_delete_input_file=True
                        )
                        batch_id = batch_job.id
                    
                    # 等待任务完成
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    while True:
                        status = client.batches.retrieve(batch_id)
                        status_text.text(f"当前状态: {status.status}")
                        
                        if status.status == "completed":
                            break
                        elif status.status in ["failed", "expired", "cancelled"]:
                            st.error("处理失败！")
                            return
                        
                        time.sleep(5)
                    
                    # 下载结果
                    with st.spinner("下载处理结果..."):
                        content = client.files.content(status.output_file_id)
                        content.write_to_file("batch_results.jsonl")
                        
                        with open("batch_results.jsonl", "r", encoding='utf-8') as f:
                            results = process_batch_results(f.read())
                    
                    # 创建结果DataFrame
                    result_df = pd.DataFrame({
                        '摘要': df['摘要'],
                        '分类结果': results
                    })
                    
                    # 显示处理结果
                    st.write("处理结果预览：")
                    st.dataframe(result_df)
                    
                    # 提供下载功能
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        result_df.to_excel(writer, index=False)
                    
                    st.download_button(
                        label="下载处理结果",
                        data=output.getvalue(),
                        file_name="classification_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
            except Exception as e:
                st.error(f"处理文件时出错：{str(e)}")

if __name__ == "__main__":
    main()
