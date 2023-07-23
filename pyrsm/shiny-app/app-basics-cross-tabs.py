from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from pathlib import Path
from shiny import App
from pyrsm.radiant.cross_tabs import basics_cross_tabs
import pyrsm.radiant.utils as ru

www_dir = Path(__file__).parent.parent / "radiant" / "www"
app_static = StaticFiles(directory=www_dir, html=False)

data_dct, descriptions_dct = ru.get_dfs(pkg="basics", name="newspaper")
rc = basics_cross_tabs(data_dct, descriptions_dct, code=True)

routes = [
    Mount("/www", app=app_static),
    Mount("/", app=App(rc.shiny_ui(), rc.shiny_server, debug=False)),
]
app = Starlette(debug=True, routes=routes)
