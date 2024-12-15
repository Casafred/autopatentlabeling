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

def create_batch_jsonl(df, classification_system):
    """创建batch处理所需的jsonl文件内容"""
    jsonl_content = StringIO()
    
    # 构建分类体系的层级描述
    system_description = "分类体系层级结构：\n"
    for level1_label, level1_data in classification_system.items():
        system_description += f"一级分类 - {level1_label}：{level1_data['description']}\n"
        if 'children' in level1_data:
            for level2_label, level2_data in level1_data['children'].items():
                system_description += f"  ├─ 二级分类 - {level2_label}：{level2_data['description']}\n"
                if 'children' in level2_data:
                    for level3_label, level3_data in level2_data['children'].items():
                        system_description += f"  │  ├─ 三级分类 - {level3_label}：{level3_data['description']}\n"
    
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
                        "content": "你是一个电动工具领域专利文本分类专家，擅长将专利摘要中的主要技术内容与多级技术分类体系中的标签进行对应。"
                    },
                    {
                        "role": "user",
                        "content": f"""
                        请根据以下多级分类体系对专利文本进行分类，需要同时给出各个层级的分类标签：

                        {system_description}
                        
                        专利摘要：{row['摘要']}
                        
                        请以JSON格式返回，包含以下字段：
                        1. level1_category: 一级分类标签
                        2. level2_category: 二级分类标签
                        3. level3_category: 三级分类标签（如果有）
                        4. reason: 分类理由
                        """
                    }
                ],
                "temperature": 0.1
            }
        }
        jsonl_content.write(json.dumps(request, ensure_ascii=False) + '\n')
    
    return jsonl_content.getvalue()

def add_classification_level(parent_dict, level_name, description):
    """添加分类层级"""
    if level_name not in parent_dict:
        parent_dict[level_name] = {
            "description": description,
            "children": {}
        }
    return parent_dict[level_name]["children"]

def save_classification_system(classification_system):
    """保存分类体系为JSON文件"""
    return json.dumps(classification_system, ensure_ascii=False, indent=2)

def load_classification_system(json_str):
    """从JSON字符串加载分类体系"""
    return json.loads(json_str)

def main():
    st.title("ChervonIP专利数据库分类工具")
    
    # 创建两个主要区域
    setup_col, upload_col = st.columns(2)
    
    with setup_col:
        st.subheader("1. 设置工具品类技术分类系统")
        
        # ZhipuAI API密钥输入
        api_key = st.text_input("输入智谱AI API密钥", type="password")
        
        # 分类体系配置文件上传
        config_file = st.file_uploader("上传分类体系配置文件（可选）", type=['json'])
        
        if config_file is not None:
            classification_system = load_classification_system(config_file.getvalue().decode('utf-8'))
            st.success("成功加载分类体系配置！")
        else:
            # 手动创建分类体系
            classification_system = {}
            
            # 一级分类
            num_level1 = st.number_input("一级分类数量", min_value=1, value=1)
            for i in range(num_level1):
                level1_name = st.text_input(f"一级分类 {i+1} 标签名称", key=f"l1_name_{i}")
                level1_desc = st.text_input(f"一级分类 {i+1} 描述", key=f"l1_desc_{i}")
                
                if level1_name and level1_desc:
                    level2_dict = add_classification_level(classification_system, level1_name, level1_desc)
                    
                    # 在一级分类下添加二级分类
                    with st.expander(f"添加 {level1_name} 的二级分类"):
                        num_level2 = st.number_input(f"{level1_name} 的二级分类数量", min_value=0, value=0, key=f"num_l2_{i}")
                        
                        for j in range(num_level2):
                            level2_name = st.text_input(f"二级分类 {j+1} 标签名称", key=f"l2_name_{i}_{j}")
                            level2_desc = st.text_input(f"二级分类 {j+1} 描述", key=f"l2_desc_{i}_{j}")
                            
                            if level2_name and level2_desc:
                                level3_dict = add_classification_level(level2_dict, level2_name, level2_desc)
                                
                                # 在二级分类下添加三级分类
                                with st.expander(f"添加 {level2_name} 的三级分类"):
                                    num_level3 = st.number_input(f"{level2_name} 的三级分类数量", min_value=0, value=0, key=f"num_l3_{i}_{j}")
                                    
                                    for k in range(num_level3):
                                        level3_name = st.text_input(f"三级分类 {k+1} 标签名称", key=f"l3_name_{i}_{j}_{k}")
                                        level3_desc = st.text_input(f"三级分类 {k+1} 描述", key=f"l3_desc_{i}_{j}_{k}")
                                        
                                        if level3_name and level3_desc:
                                            add_classification_level(level3_dict, level3_name, level3_desc)
        
        # 保存分类体系
        if st.button("保存分类体系"):
            if classification_system:
                config_json = save_classification_system(classification_system)
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
