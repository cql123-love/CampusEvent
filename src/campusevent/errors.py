"""Shared business exception without a policy-to-service dependency."""


class BusinessError(Exception):
    """业务规则校验失败，携带面向用户的提示。"""
