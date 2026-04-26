class ServiceRegistry:
    """服务注册表，持有所有共享服务实例。
    存储在 app.extensions['registry']，路由通过 current_app 访问。
    """
    def __init__(self):
        self.session_store = None
        self.permission_mgr = None
        self.tunnel = None
        self.llm_client = None
        self.agent = None
        self.current_model = "deepseek-v4-pro"
        self.cancel_flags = {}  # session_id -> threading.Event
