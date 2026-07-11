from openwakeword.model import Model

from config import WAKE_WORD_MODEL_PATH, WAKE_WORD_NAME


def create_wakeword_model():
    if WAKE_WORD_MODEL_PATH:
        wakeword_models = [WAKE_WORD_MODEL_PATH]
    elif WAKE_WORD_NAME:
        wakeword_models = [WAKE_WORD_NAME]
    else:
        raise RuntimeError(
            "No wake word configured. Train a custom 'Hey Zhora' model and set "
            "WAKE_WORD_MODEL_PATH in .env, or set WAKE_WORD_NAME to a pretrained "
            "openWakeWord model as a temporary stand-in. See README for training instructions."
        )
    return Model(wakeword_models=wakeword_models, inference_framework="onnx")
