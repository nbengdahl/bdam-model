"""JSON bridge preserving arbitrary MATLAB table column names."""
import sys
from pathlib import Path
from bdam import Study
from bdam_runtime import read, write


def main(request_path, response_path):
    request=read(request_path)
    settings=request.get("settings")
    if settings is not None:
        settings=dict(settings)
        if "shared_file" in settings:
            settings["shared"]=read(settings.pop("shared_file"))
        existing=Path(request["root"])/"study.json"
        if existing.is_file():
            saved=read(existing)["settings"]
            if "execution" in settings:
                settings["execution"]={**saved["execution"],**settings["execution"]}
            settings={**saved,**settings}
    study=Study(request["root"],settings)
    action=request["action"]
    if action in ("submit","evaluate"):
        result=study.submit(request["cases"],request["batch_id"])
    if action in ("prepare","evaluate","collect"):
        result=getattr(study,action)(request["batch_id"])
    write(response_path,result)


if __name__=="__main__":
    main(*sys.argv[1:])
