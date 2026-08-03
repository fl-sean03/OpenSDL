from .models import Apparatus, Scan, Signal


def get_pack():
    return {
        "name": "physics",
        "version": "v0alpha1",
        "models": {
            name: model.model_json_schema()
            for name, model in {"Apparatus": Apparatus, "Scan": Scan, "Signal": Signal}.items()
        },
    }
