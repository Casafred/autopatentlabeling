import streamlit as st
import pandas as pd
from io import BytesIO, StringIO
import json
import time
import tempfile
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

def recursive_update(system, path, name, description):
    """递归更新分类体系"""
    parts = path.split('/')
    for part in parts[:-1]:
        if part not in system:
            system[part] = {'description': '', 'children': {}}  # Create missing part if necessary
        system = system[part]['children']
    
    # Make sure the final part exists
    if parts[-1] not in system:
        system[parts[-1]] = {'description': '', 'children': {}}
    
    system[parts[-1]]['children'][name] = {"description": description, "children": {}}


def format_classification_system(classification_system, level=1):
    """格式化分类体系供显示"""
    formatted = []
    for name, data in classification_system.items():
        formatted.append(f"{'  ' * (level - 1)}[L{level}] {name}: {data['description']}")
        if data['children']:
            formatted.extend(format_classification_system(data['children'], level + 1))
    return formatted

def create_classification_system():
    """创建分类体系"""
    classification_system = {}
    
    # 设置分类级数
    num_levels = st.number_input("设置分类级数", min_value=1, max_value=5, value=1)
    
    for level in range(1, num_levels + 1):
        st.markdown(f"### 第{level}级分类设置")
        parent_categories = ["root"] if level == 1 else list(st.session_state[f"level_{level-1}_categories"].keys())
        
        level_categories = {}
        for parent in parent_categories:
            st.markdown(f"#### 在 {parent if parent != 'root' else '根目录'} 下创建子分类")
            num_subcategories = st.number_input(
                f"{parent} 的子分类数量", min_value=0, value=1, key=f"num_subcat_{level}_{parent}"
            )
            for i in range(num_subcategories):
                col1, col2 = st.columns(2)
                with col1:
                    name = st.text_input(f"分类名称 {i+1}", key=f"name_{level}_{parent}_{i}")
                with col2:
                    desc = st.text_input(f"分类描述 {i+1}", key=f"desc_{level}_{parent}_{i}")
                
                if name and desc:
                    level_categories[f"{parent}/{name}" if parent != 'root' else name] = {"description": desc, "children": {}}
                    recursive_update(classification_system, parent, name, desc)
        
        st.session_state[f"level_{level}_categories"] = level_categories
    
    return classification_system

def create_batch_jsonl(df, classification_system):
    """创建batch处理所需的jsonl文件内容"""
    jsonl_content = StringIO()

    system_description = "\n".join(format_classification_system(classification_system))

    for idx, row in df.iterrows():
        if not row['摘要']:
            continue  # 跳过空摘要

        # 构建符合ZhipuAI要求的jsonl请求格式
        request = {
            "custom_id": f"request-{idx}",  # 每个请求必须包含唯一的 custom_id
            "method": "POST",
            "url": "/v4/chat/completions", 
            "body": {
                "model": "glm-4",  # 使用特定的模型
                "messages": [
                    {
                        "role": "system",
                        "content": """
                        你是一个电动工具领域专利文本分类专家。
                        分类时请注意：
                        1. 必须从第一级开始逐级分类
                        2. 每个分类都需要给出具体的理由
                        3. 如果某个分支下没有合适的子分类，可以只到上一级为止
                        4. 分类结果要确保层级对应关系正确"""
                    },
                    {
                        "role": "user",
                        "content": f"""
                        请根据以下分类体系对专利文本进行多级分类：

                        分类体系：
                        {system_description}

                        专利摘要：
                        {row['摘要']}
                        
                        请按以下JSON格式返回分类结果：
                        {{
                            "classification_path": [
                                {{
                                    "level": 1,
                                    "category": "分类名称",
                                    "confidence": 0.95,
                                    "reason": "选择该分类的具体理由"
                                }},
                                ...
                            ],
                            "summary": "整体分类分析说明"
                        }}
                        """
                    }
                ],
                "temperature": 0.1
            }
        }

        # 将每个请求的 JSON 写入 jsonl_content
        jsonl_content.write(json.dumps(request, ensure_ascii=False) + '\n')

    # 创建临时文件并写入内容
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as temp_file:
        temp_file.write(jsonl_content.getvalue().encode('utf-8'))
        temp_file_path = temp_file.name

    return temp_file_path

def process_batch_upload(client, jsonl_file_path):
    """上传 Batch 文件并创建 Batch 任务"""
    result = client.files.create(
        file=open(jsonl_file_path, "rb"),
        purpose="batch"
    )
    
    file_id = result.id
    print(f"文件上传成功，文件ID: {file_id}")
    
    # 创建 Batch 任务
    create = client.batches.create(
        input_file_id=file_id,
        endpoint="/v4/chat/completions", 
        auto_delete_input_file=True,
        metadata={
            "description": "专利分类任务"
        }
    )
    
    batch_id = create.id
    print(f"Batch 任务创建成功，任务ID: {batch_id}")
    
    return batch_id

def list_batches(client, limit=10):
    """列出 Batch 任务列表"""
    batch_list = client.batches.list(limit=limit)
    return batch_list

def check_batch_status(client, batch_id):
    """检查 Batch 任务状态"""
    status = client.batches.retrieve(batch_id)
    return status

def download_batch_result(client, file_id, save_path):
    """下载 Batch 结果"""
    content = client.files.content(file_id)
    
    # 将结果保存为 JSONL 文件
    with open(save_path, "wb") as f:
        content.write_to_file(f)
    print(f"Batch 结果已保存为 {save_path}")

    return save_path

def main():
    st.title("ChervonIP专利数据库分类工具")
    
    setup_col, upload_col = st.columns(2)
    
    with setup_col:
        st.subheader("1. 设置工具品类技术分类系统")
        
        api_key = st.text_input("输入智谱AI API密钥", type="password")
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
            classification_system = create_classification_system()
        
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
                    # 创建 ZhipuAI 客户端
                    client = ZhipuAI(api_key=api_key)

                    # 生成jsonl文件路径
                    jsonl_file_path = create_batch_jsonl(df, classification_system)
                    
                    # 上传文件并创建 Batch 任务
                    batch_id = process_batch_upload(client, jsonl_file_path)
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    while True:
                        status = check_batch_status(client, batch_id)
                        status_text.text(f"当前状态: {status.status}")
                        
                        if status.status == "completed":
                            break
                        elif status.status in ["failed", "expired", "cancelled"]:
                            st.error("处理失败！")
                            return
                        
                        time.sleep(5)
                    
                    with st.spinner("下载处理结果..."):
                        download_batch_result(client, status.output_file_id, "batch_output.jsonl")
                        
                        # 假设转换为 Excel 并下载
                        # 解析并转换文件为 Excel，展示下载按钮等

            except Exception as e:
                st.error(f"处理文件时出错：{str(e)}")

if __name__ == "__main__":
    main()
