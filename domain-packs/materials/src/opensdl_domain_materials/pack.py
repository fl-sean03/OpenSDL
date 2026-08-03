from .models import Composition, ProcessStep, PropertyMeasurement, Specimen


def get_pack():
    return {
        "name": "materials",
        "version": "v0alpha1",
        "models": {
            name: model.model_json_schema()
            for name, model in {
                "Composition": Composition,
                "ProcessStep": ProcessStep,
                "Specimen": Specimen,
                "PropertyMeasurement": PropertyMeasurement,
            }.items()
        },
    }
