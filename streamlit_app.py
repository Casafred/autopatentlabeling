import streamlit as st
import pandas as pd
import openai
from io import BytesIO

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

# 初始化会话状态
if 'classification_system' not in st.session_state:
    st.session_state.classification_system = {}
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None

def process_text_with_openai(text, classification_system, api_key):
    """调用OpenAI API进行文本分类"""
    openai.api_key = api_key
    
    # 构建提示词
    prompt = f"""
    请根据以下分类体系对文本进行分类，并说明分类理由：
    分类体系：{classification_system}
    
    文本内容：{text}
    
    请以JSON格式返回，包含两个字段：
    1. category: 分类标签
    2. reason: 分类理由
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "你是一个文本分类专家。"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return str(e)

def main():
    st.title("文本分类分析工具")
    
    # 创建三个主要区域
    setup_col, upload_col = st.columns(2)
    
    with setup_col:
        st.subheader("1. 设置分类系统")
        
        # OpenAI API密钥输入
        api_key = st.text_input("输入OpenAI API密钥", type="password")
        
        # 分类级别设置
        levels = st.number_input("设置分类级别数", min_value=1, max_value=5, value=1)
        
        # 动态创建分类系统输入界面
        classification_system = {}
        for level in range(1, levels + 1):
            st.markdown(f"#### 第{level}级分类")
            
            # 为每个级别创建可扩展的标签输入
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
        
        # 保存分类系统
        if st.button("保存分类系统"):
            st.session_state.classification_system = classification_system
            st.success("分类系统已保存！")
    
    with upload_col:
        st.subheader("2. 上传和处理数据")
        
        # 文件上传
        uploaded_file = st.file_uploader("上传Excel文件", type=['xlsx', 'xls'])
        
        if uploaded_file is not None:
            try:
                df = pd.read_excel(uploaded_file)
                
                # 检查是否存在"摘要"列
                if "摘要" not in df.columns:
                    st.error("上传的Excel文件中没有找到"摘要"列！")
                    return
                
                # 显示原始数据预览
                st.write("原始数据预览：")
                st.dataframe(df.head())
                
                # 处理数据
                if st.button("开始处理") and api_key:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    results = []
                    total_rows = len(df)
                    
                    for idx, row in df.iterrows():
                        status_text.text(f"处理第 {idx+1}/{total_rows} 条数据...")
                        
                        # 调用OpenAI API进行分类
                        result = process_text_with_openai(
                            row["摘要"], 
                            st.session_state.classification_system,
                            api_key
                        )
                        results.append(result)
                        
                        # 更新进度条
                        progress_bar.progress((idx + 1) / total_rows)
                    
                    # 创建结果DataFrame
                    result_df = pd.DataFrame({
                        "摘要": df["摘要"],
                        "分类结果": results
                    })
                    
                    # 保存处理结果
                    st.session_state.processed_data = result_df
                    
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
