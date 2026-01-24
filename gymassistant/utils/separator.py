def get_action_part(action: str) -> str:
    parts = action.split('/', 1)
    return parts[1] if len(parts) > 1 else parts[0]
