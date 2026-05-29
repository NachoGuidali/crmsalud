ACTION_REGISTRY = {}


def register_action(name):
    def decorator(fn):
        ACTION_REGISTRY[name] = fn
        return fn
    return decorator
