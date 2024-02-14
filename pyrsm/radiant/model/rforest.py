from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.requests import Request as StarletteRequest
from shiny import App, ui, render, reactive, Inputs, Outputs, Session, req
from pathlib import Path
import webbrowser
import nest_asyncio
import uvicorn
import signal
import os
import sys
import tempfile
import pyrsm as rsm
import pyrsm.radiant.utils as ru
import pyrsm.radiant.model.model_utils as mu

choices = {
    "None": "None",
    "pred": "Prediction plots",
    "pdp": "Partial Dependence plots (PDP)",
    "vimp": "Permutation importance",
}


def summary_extra(self):
    max_features = {"sqrt": "sqrt", "log2": "log2"}
    max_features.update({v: v for v in range(1, 101, 1)})
    return (
        (
            ui.input_radio_buttons(
                "mod_type",
                None,
                selected=self.state.get("mod_type", "classification"),
                choices=["classification", "regression"],
                inline=True,
            ),
            ru.make_side_by_side(
                ui.input_numeric(
                    "n_estimators",
                    "# trees:",
                    value=self.state.get("n_estimators", 100),
                ),
                ui.input_select(
                    "max_features",
                    "Max features:",
                    choices=max_features,
                    selected=self.state.get("max_features", None),
                ),
            ),
            ru.make_side_by_side(
                ui.input_numeric(
                    "min_samples_leaf",
                    "Min node size:",
                    value=self.state.get("min_samples_leaf", 1),
                ),
                ui.input_numeric(
                    "max_samples",
                    "Sample fraction:",
                    value=self.state.get("max_samples", 1.0),
                    min=0,
                    max=1,
                    step=0.1,
                ),
            ),
            ui.input_numeric(
                "random_state",
                "Random seed:",
                value=self.state.get("random_state", 1234),
            ),
            ru.input_return_text_area(
                "extra_args",
                label="Additional arguments:",
                placeholder="max_depth=5, n_jobs=-1",
                value=self.state.get("extra_args", ""),
            ),
        ),
    )


def plots_extra(self):
    return (
        ui.panel_conditional(
            "input.plots == 'pred'",
            ui.output_ui("ui_incl_evar"),
            ui.output_ui("ui_incl_interactions"),
        ),
    )


class model_rforest:
    def __init__(
        self, datasets: dict, descriptions=None, state=None, code=True, navbar=None
    ) -> None:
        ru.init(
            self,
            datasets,
            descriptions=descriptions,
            state=state,
            code=code,
            navbar=navbar,
        )

    def shiny_ui(self, request: StarletteRequest):
        return ui.page_navbar(
            ru.head_content(),
            ui.nav(
                "Model > Random Forest",
                ui.row(
                    ui.column(
                        3,
                        ru.ui_data(self),
                        ru.ui_summary(summary_extra(self)),
                        mu.ui_predict(self, show_ci=False),
                        ru.ui_plot(self, choices, plots_extra(self)),
                    ),
                    ui.column(8, ru.ui_main_model()),
                ),
            ),
            self.navbar,
            ru.ui_help(
                "https://github.com/vnijs/pyrsm/blob/main/examples/model/model-rforest-classification.ipynb",
                "Random Forest (classification) example notebook",
            ),
            ru.ui_stop(),
            title="Radiant for Python",
            inverse=False,
            id="navbar_id",
        )

    def shiny_server(self, input: Inputs, output: Outputs, session: Session):
        # --- section standard for all apps ---
        get_data = ru.make_data_elements(self, input, output, session)

        def update_state():
            with reactive.isolate():
                ru.dct_update(self, input)

        session.on_ended(update_state)

        # --- section standard for all model apps ---
        ru.reestimate(input)

        # --- section unique to each app ---
        mu.make_model_inputs(
            self,
            input,
            output,
            get_data,
            {"classification": "isBin", "regression": "isNum"},
        )

        @output(id="ui_lev")
        @render.ui
        def ui_lev():
            req(input.rvar())
            levs = list(get_data()["data"][input.rvar()].unique())
            return ui.input_select(
                id="lev",
                label="Choose level:",
                selected=self.state.get("lev", None),
                choices=levs,
            )

        mu.make_int_inputs(self, input, output, get_data)
        show_code, estimate = mu.make_estimate(
            self, input, output, get_data, fun="rforest", ret="rf", debug=False
        )
        mu.make_summary(
            self,
            input,
            output,
            session,
            show_code,
            estimate,
            ret="rf",
            sum_fun=rsm.model.rforest.summary,
        )
        mu.make_predict(
            self,
            input,
            output,
            session,
            show_code,
            estimate,
            ret="rf",
            pred_fun=rsm.model.rforest.predict,
            show_ci=False,
        )
        mu.make_plot(
            self,
            input,
            output,
            session,
            show_code,
            estimate,
            ret="rf",
        )

        # --- section standard for all apps ---
        # stops returning code if moved to utils
        @reactive.Effect
        @reactive.event(input.stop, ignore_none=True)
        async def stop_app():
            rsm.md(f"```python\n{self.stop_code}\n```")
            await session.app.stop()
            os.kill(os.getpid(), signal.SIGTERM)


def rforest(
    data_dct: dict = None,
    descriptions_dct: dict = None,
    state: dict = None,
    code: bool = True,
    host: str = "",
    port: int = 8000,
    log_level: str = "warning",
    debug: bool = False,
):
    """
    Launch a Radiant-for-Python app for Random Forest
    """
    host = ru.set_host(host)
    if data_dct is None:
        data_dct, descriptions_dct = ru.get_dfs(pkg="model", name="titanic")
    rc = model_rforest(data_dct, descriptions_dct, state=state, code=code)
    nest_asyncio.apply()
    webbrowser.open(f"http://{host}:{port}")
    print(f"Listening on http://{host}:{port}")
    ru.message()

    # redirect stdout and stderr to the temporary file
    if not debug:
        org_stdout = sys.stdout
        org_stderr = sys.stderr
        temp = tempfile.NamedTemporaryFile()
        temp_file = open(temp.name, "w")
        sys.stdout = temp_file
        sys.stderr = temp_file

    app = App(rc.shiny_ui, rc.shiny_server)
    www_dir = Path(__file__).parent.parent.parent / "radiant" / "www"
    app_static = StaticFiles(directory=www_dir, html=False)

    routes = [
        Mount("/www", app=app_static),
        Mount("/", app=app),
    ]

    uvicorn.run(
        Starlette(debug=debug, routes=routes),
        host=host,
        port=port,
        log_level=log_level,
    )

    if not debug:
        sys.stdout = org_stdout
        sys.stderr = org_stderr
        temp_file.close()


if __name__ == "__main__":
    # titanic, titanic_description = rsm.load_data(pkg="data", name="titanic")
    # rforest({"titanic": titanic}, {"titanic": titanic_description}, code=True)
    rforest(debug=False)
