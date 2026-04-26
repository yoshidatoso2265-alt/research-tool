"""Secrets ローダー。

優先順位: 環境変数 > Streamlit secrets。
未設定なら None を返す（呼び出し側で graceful degrade する）。
"""
import os
from typing import Optional


def get_apify_token() -> Optional[str]:
    if v := os.environ.get("APIFY_TOKEN"):
        return v.strip() or None
    try:
        import streamlit as st
        # st.secrets はファイル存在しないと StreamlitSecretNotFoundError を出すので catch
        v = st.secrets.get("APIFY_TOKEN")
        return (v.strip() or None) if v else None
    except Exception:
        return None
