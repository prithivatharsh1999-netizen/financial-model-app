import streamlit as st
import pandas as pd
import google.generativeai as genai
import json

# 1. Page Setup & Sidebar
st.set_page_config(layout="wide")
st.title("Financial Model Builder & Forecaster")

# --- NEW: RATIO SELECTION SIDEBAR ---
st.sidebar.header("📊 Metrics & Ratios")
st.sidebar.write("Select the historical ratios you want to calculate:")

selected_ratios = st.sidebar.multiselect(
    "Available Ratios",
    ["Gross Margin (%)", "Net Margin (%)", "Current Ratio", "Return on Equity (ROE)"],
    default=["Net Margin (%)"] # Default selection
)
st.sidebar.divider()
# ------------------------------------

st.sidebar.header("⚙️ Forecast Assumptions")
scenario = st.sidebar.selectbox(
    "Choose Scenario", 
    ["Ideal Case (Base)", "Best Case (Upside)", "Least Case (Downside)", "Custom"]
)

if scenario == "Custom":
    st.sidebar.markdown("### Custom Inputs")
    custom_rev_growth = st.sidebar.number_input("Target Revenue Growth (%)", value=10.0, step=1.0)
    custom_margin = st.sidebar.number_input("Target Net Margin (%)", value=15.0, step=1.0)
else:
    st.sidebar.info(f"The AI will automatically calculate assumptions for the **{scenario}**.")

st.write("Upload raw financial data to clean it, calculate custom ratios, and build a forecast.")

# 2. Secure API Key Input
api_key = st.text_input("Enter your Google Gemini API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)
    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not valid_models:
            st.error("No compatible AI models found.")
        else:
            model = genai.GenerativeModel(valid_models[0]) 
    except Exception as e:
        st.error(f"Error connecting to Google AI: {e}")

    # 3. File Uploader
    uploaded_file = st.file_uploader("Upload your Excel or CSV file here", type=["xlsx", "xls", "csv"])

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            # 4. The Engine
            if st.button(f"Generate Model: {scenario}"):
                display_name = valid_models[0].replace("models/", "")
                
                with st.spinner(f"AI ({display_name}) is extracting comprehensive financial data..."): 
                    
                    csv_data = df.to_csv(index=False)
                    
                    # NEW AI PROMPT: Asking for the raw ingredients for all possible ratios
                    prompt_history = f"""
                    Extract the historical numerical data for the following categories across all available years:
                    1. Revenue
                    2. COGS (Cost of Goods Sold or Material Cost)
                    3. Net Income (Profit After Tax)
                    4. Current Assets
                    5. Current Liabilities
                    6. Total Equity (Shareholder's Funds)
                    
                    Return ONLY a valid JSON object. If a data point is missing, insert 0. Format exactly like this:
                    {{
                        "Revenue": {{"Mar 2021": 1000, "Mar 2022": 1200}},
                        "COGS": {{"Mar 2021": 600, "Mar 2022": 700}},
                        "Net Income": {{"Mar 2021": 100, "Mar 2022": 150}},
                        "Current Assets": {{"Mar 2021": 500, "Mar 2022": 550}},
                        "Current Liabilities": {{"Mar 2021": 250, "Mar 2022": 300}},
                        "Total Equity": {{"Mar 2021": 800, "Mar 2022": 900}}
                    }}
                    Raw Data:
                    {csv_data}
                    """
                    
                    response_history = model.generate_content(prompt_history)
                    
                    try:
                        raw_json_text = response_history.text.replace("```json", "").replace("```", "").strip()
                        clean_data = json.loads(raw_json_text)
                        clean_df = pd.DataFrame(clean_data)
                        
                        # --- NEW: DYNAMIC RATIO CALCULATOR ---
                        # Python will only calculate what the user selected in the sidebar
                        if "Gross Margin (%)" in selected_ratios:
                            clean_df["Gross Margin (%)"] = ((clean_df["Revenue"] - clean_df["COGS"]) / clean_df["Revenue"]) * 100
                        
                        if "Net Margin (%)" in selected_ratios:
                            clean_df["Net Margin (%)"] = (clean_df["Net Income"] / clean_df["Revenue"]) * 100
                            
                        if "Current Ratio" in selected_ratios:
                            clean_df["Current Ratio"] = clean_df["Current Assets"] / clean_df["Current Liabilities"]
                            
                        if "Return on Equity (ROE)" in selected_ratios:
                            clean_df["ROE (%)"] = (clean_df["Net Income"] / clean_df["Total Equity"]) * 100
                        # ---------------------------------------

                        st.subheader("1. Historical Data & Selected Ratios")
                        
                        # Create a list of columns to display: core items + user selected ratios
                        display_cols = ["Revenue", "Net Income"] + [col for col in clean_df.columns if "%" in col or "Ratio" in col]
                        st.dataframe(clean_df[display_cols].style.format("{:,.2f}"))
                        
                        # 5. 5-Year Forecast
                        st.divider()
                        st.subheader(f"2. 5-Year Forecast ({scenario})")
                        
                        if scenario == "Custom":
                            rev_growth_rate = custom_rev_growth / 100.0
                            net_margin_rate = custom_margin / 100.0
                            st.success(f"Applying Custom Assumptions: Revenue Growth = **{custom_rev_growth}%**, Net Margin = **{custom_margin}%**")
                        else:
                            with st.spinner("AI is determining optimal forecast assumptions..."):
                                prompt_assumptions = f"""
                                Based on this historical data: {clean_df[["Revenue", "Net Income"]].to_string()}
                                Calculate realistic forward-looking assumptions for a '{scenario}' scenario.
                                Return ONLY a valid JSON object like this:
                                {{"Revenue Growth (%)": 12.5, "Net Margin (%)": 15.0}}
                                """
                                response_assump = model.generate_content(prompt_assumptions)
                                assump_json = response_assump.text.replace("```json", "").replace("```", "").strip()
                                assumptions = json.loads(assump_json)
                                
                                rev_growth_rate = assumptions["Revenue Growth (%)"] / 100.0
                                net_margin_rate = assumptions["Net Margin (%)"] / 100.0
                                st.success(f"AI Calculated Assumptions: Revenue Growth = **{assumptions['Revenue Growth (%)']}%**, Net Margin = **{assumptions['Net Margin (%)']}%**")

                        latest_revenue = clean_df.iloc[-1]["Revenue"]
                        forecast_data = []
                        current_rev = latest_revenue
                        
                        for i in range(1, 6):
                            current_rev = current_rev * (1 + rev_growth_rate)
                            current_net_income = current_rev * net_margin_rate
                            forecast_data.append({
                                "Year": f"Year {i}", 
                                "Projected Revenue": current_rev, 
                                "Projected Net Income": current_net_income
                            })
                            
                        forecast_df = pd.DataFrame(forecast_data).set_index("Year")
                        st.dataframe(forecast_df.style.format("{:,.2f}"))
                        
                    except Exception as json_error:
                        st.error("Error formatting data. The AI might have struggled with this specific file's layout.")
                        st.write(response_history.text)
                    
        except Exception as e:
            st.error(f"Error processing the file: {e}")
else:
    st.info("Please enter your API key to unlock the app features.")