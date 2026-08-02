from .models import Chemical, Reaction, Solution

def get_pack():
    return {"name":"chemistry","version":"v0alpha1","models":{name:model.model_json_schema() for name,model in {"Chemical":Chemical,"Solution":Solution,"Reaction":Reaction}.items()}}
