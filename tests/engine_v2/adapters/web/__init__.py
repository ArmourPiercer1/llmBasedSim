"""P10 web 适配测试包（SOT §11 白名单行 27–29；零函数）。

W4 波交付 = ``conftest``（4 fixture + 宿主驱动，§6.2）+
``test_session_manager``（6 平铺函数 t1–t6）+ ``test_web_api``
（5 平铺函数 t1–t5）；全部显式 session_id（DEV-P10-05 纪律）；
零 socket / 零网络（D-P10-03）。
"""
