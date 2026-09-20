DEFAULT_MODEL = "openrouter/free"

MODEL_MAP = {
    "manager": "openrouter/free",
    "marketing": "openrouter/free",
    "sales": "openrouter/free",
    "automation": "openrouter/free",
    "evaluation": "openrouter/free",
    "coding": "openrouter/free",
}


def get_model_for(role: str) -> str:
    import os

    env_key = f"{role.upper()}_MODEL"
    value = os.getenv(env_key)
    if value:
        return value

    return MODEL_MAP.get(role, DEFAULT_MODEL)
