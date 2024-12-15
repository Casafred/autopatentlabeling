import streamlit as st
import pandas as pd
from io import BytesIO, StringIO
import json
import time
from zhipuai import ZhipuAI

# 页面配置
st.set_page_config(page_title="ChervonIP专利数据库分类工具", layout="wide")

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
    .hierarchy-input {
        margin-left: 30px;
        border-left: 2px solid #e0e0e0;
        padding-left: 10px;
    }
    </style>
""", unsafe_allow_html=True)

def create_classification_system():
    """创建分类体系"""
    classification_system = {}
    
    # 设置分类级数
    num_levels = st.number_input("设置分类级数", min_value=1, max_value=5, value=1)
    
    def add_sublabels(parent_level, current_level, max_level):
        """递归添加子标签"""
        if current_level > max_level:
            return {}
            
        labels = {}
        num_labels = st.number_input(
            f"第{current_level}级标签数量" + (f" (在{parent_level}下)" if parent_level else ""),
            min_value=1,
            value=1,
            key=f"num_labels_{current_level}_{parent_level}"
        )
        
        for i in range(num_labels):
            col1, col2 = st.columns(2)
            with col1:
                label_name = st.text_input(
                    f"第{current_level}级标签{i+1}名称" + (f" (在{parent_level}下)" if parent_level else ""),
                    key=f"label_{current_level}_{parent_level}_{i}"
                )
            with col2:
                description = st.text_input(
                    f"第{current_level}级标签{i+1}描述" + (f" (在{parent_level}下)" if parent_level else ""),
                    key=f"desc_{current_level}_{parent_level}_{i}"
                )
            
            if label_name and description:
                labels[label_name] = {
                    "description": description,
                    "children": add_sublabels(label_name, current_level + 1, max_level)
                }
        
        return labels
    
    # 从第一级开始递归创建分类体系
    classification_system = add_sublabels("", 1, num_levels)
    
    return classification_system

def format_classification_system(system_dict, level=1, prefix=""):
    """格式化分类体系为字符串"""
    result = []
    for label, data in system_dict.items():
        indent = "  " * (level - 1)
        result.append(f"{indent}第{level}级分类 - {label}：{data['description']}")
        if data['children']:
            result.extend(format_classification_system(data['children'], level + 1, prefix + indent))
    return result

def create_batch_jsonl(df, classification_system):
    """创建batch处理所需的jsonl文件内容"""
    jsonl_content = StringIO()
    
    # 构建分类体系的层级描述
    system_description = "分类体系层级结构：\n" + "\n".join(format_classification_system(classification_system))
    
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
                        "content": """你是一个电动工具领域专利文本分类专家。
                        你需要对每个专利文本在每个分类层级都进行标注，并给出详细的分类理由。
                        分类结果应该遵循层级关系，确保下级分类与上级分类相对应。"""
                    },
                    {
                        "role": "user",
                        "content": f"""
                        请根据以下多级分类体系对专利文本进行分类，需要为每个层级都选择适当的分类标签：

                        {system_description}
                        
                        专利摘要：{row['摘要']}
                        
                        请以JSON格式返回，格式如下：
                        {{
                            "classifications": [
                                {{"level": 1, "category": "一级分类标签", "confidence": "分类确信度"}},
                                {{"level": 2, "category": "二级分类标签", "confidence": "分类确信度"}},
                                ...
                            ],
                            "reason": "详细的分类理由，解释为什么选择这些标签"
                        }}
                        """
                    }
                ],
                "temperature": 0.1
            }
        }
        jsonl_content.write(json.dumps(request, ensure_ascii=False) + '\n')
    
    return jsonl_content.getvalue()

def main():
    st.title("ChervonIP专利数据库分类工具")
    
    setup_col, upload_col = st.columns(2)
    
    with setup_col:
        st.subheader("1. 设置工具品类技术分类系统")
        
        # ZhipuAI API密钥输入
        api_key = st.text_input("输入智谱AI API密钥", type="password")
        
        # 分类体系配置文件上传
        config_file = st.file_uploader("上传分类体系配置文件（可选）", type=['json'])
        
        if config_file is not None:
            try:
                classification_system = json.loads(config_file.getvalue().decode('utf-8'))
                st.success("成功加载分类体系配置！")
                st.write("当前分类体系预览：")
                st.write("\n".join(format_classification_system(classification_system)))
            except Exception as e:
                st.error(f"加载配置文件失败：{str(e)}")
                classification_system = None
        else:
            # 手动创建分类体系
            classification_system = create_classification_system()
        
        # 保存分类体系
        if st.button("保存分类体系"):
            if classification_system:
                config_json = json.dumps(classification_system, ensure_ascii=False, indent=2)
                st.download_button(
                    label="下载分类体系配置文件",
                    data=config_json,
                    file_name="classification_system.json",
                    mime="application/json"
                )
                st.session_state.classification_system = classification_system
                st.success("分类体系已保存！")
            else:
                st.error("请先创建分类体系！")
    
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
