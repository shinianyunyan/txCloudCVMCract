"""
创建实例示例
"""
from core.cvm_manager import CVMManager

if __name__ == "__main__":
    manager = CVMManager(None, None, None)
    instance = manager.create(2, 4, "ap-beijing", "YourPassword123!", None, "My-CVM-Instance", None, 1)
    print(f"实例创建成功！")
    print(f"实例ID: {instance['InstanceId']}")
    print(f"区域: {instance['Region']}")
    print(f"状态: {instance['Status']}")
