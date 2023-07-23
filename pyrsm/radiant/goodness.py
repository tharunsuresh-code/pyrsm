from shiny import App, render, ui, reactive, Inputs, Outputs, Session
import webbrowser, nest_asyncio, uvicorn
import signal, io, os, sys, tempfile
import pyrsm as rsm
from contextlib import redirect_stdout
import pyrsm.radiant.utils as ru
import pyrsm.radiant.model_utils as mu

choices = {
    "observed": "Observed",
    "expected": "Expected",
    "chisq": "Chi-squared",
    "dev_std": "Deviation std.",
}


def ui_summary():
    return ui.panel_conditional(
        "input.tabs == 'Summary'",
        ui.panel_well(
            ui.output_ui("ui_var"),
            ru.input_return_text_area(
                "probs",
                label="Probabilities:",
                placeholder="Insert list [1/2, 1/2]",
                value=None,
            ),
            ui.input_checkbox_group(
                id="output",
                label="Select output tables:",
                choices=choices,
            ),
        ),
    )


plots = {"None": "None"}
plots.update(choices)


class basics_goodness:
    def __init__(self, datasets: dict, descriptions=None, code=True) -> None:
        ru.init(self, datasets, descriptions=descriptions, code=code)

    def shiny_ui(self, *args):
        return ui.page_navbar(
            ru.head_content(),
            ui.nav(
                "<< Basics > Goodness-of-fit >>",
                ui.row(
                    ui.column(
                        3,
                        ru.ui_data(self),
                        ui_summary(),
                        ru.ui_plot(plots),
                    ),
                    ui.column(8, ru.ui_main_basics()),
                ),
            ),
            *args,
            ru.ui_help(
                "https://github.com/vnijs/pyrsm/blob/main/examples/basics-goodness.ipynb",
                "Goodness-of-fit example notebook",
            ),
            ru.ui_stop(),
            title="Radiant for Python",
            inverse=True,
            id="navbar_id",
        )

    def shiny_server(self, input: Inputs, output: Outputs, session: Session):
        # --- section standard for all apps ---
        get_data = ru.make_data_elements(self, input, output, session)

        # --- section unique to each app ---
        @output(id="ui_var")
        @render.ui
        def ui_var1():
            isCat = get_data()["var_types"]["isCat"]
            return ui.input_select(
                id="var",
                label="Select a categorical variable:",
                selected=None,
                choices=isCat,
            )

        def estimation_code():
            data_name, code = (get_data()[k] for k in ["data_name", "code"])

            if ru.is_empty(input.probs()):
                probs = None
            else:
                probs = input.probs()

            args = {
                "data": f"""{{"{data_name}": {data_name}}}""",
                "var": input.var(),
                "probs": probs,
            }

            args_string = ru.drop_default_args(
                args, rsm.basics.goodness, ignore=["data", "probs"]
            )
            return f"""rsm.basics.goodness({args_string})""", code

        show_code, estimate = mu.make_estimate(
            self,
            input,
            output,
            get_data,
            fun="basics.goodness",
            ret="gf",
            ec=estimation_code,
            run=False,
            debug=True,
        )

        def summary_code():
            args = [c for c in input.output()]
            return f"""gf.summary(output={args})"""

        mu.make_summary(
            self,
            input,
            output,
            session,
            show_code,
            estimate,
            ret="gf",
            sum_fun=rsm.basics.goodness.summary,
            sc=summary_code,
        )

        def plot_code():
            return f"""gf.plot(plots="{input.plots()}")"""

        mu.make_plot(
            self,
            input,
            output,
            session,
            show_code,
            estimate,
            ret="gf",
            pc=plot_code,
        )

        # --- section standard for all apps ---
        # stops returning code if moved to utils
        @reactive.Effect
        @reactive.event(input.stop, ignore_none=True)
        async def stop_app():
            rsm.md(f"```python\n{self.stop_code}\n```")
            await session.app.stop()
            os.kill(os.getpid(), signal.SIGTERM)


def goodness(
    data_dct: dict = None,
    descriptions_dct: dict = None,
    code: bool = True,
    host: str = "0.0.0.0",
    port: int = 8000,
    log_level: str = "warning",
):
    """
    Launch a Radiant-for-Python app for goodness of fit analysis
    """
    if data_dct is None:
        data_dct, descriptions_dct = ru.get_dfs(pkg="basics", name="newspaper")
    rc = basics_goodness(data_dct, descriptions_dct, code=code)
    nest_asyncio.apply()
    webbrowser.open(f"http://{host}:{port}")
    print(f"Listening on http://{host}:{port}")
    ru.message()

    # redirect stdout and stderr to the temporary file
    temp = tempfile.NamedTemporaryFile()
    sys.stdout = open(temp.name, "w")
    sys.stderr = open(temp.name, "w")

    uvicorn.run(
        App(rc.shiny_ui(), rc.shiny_server),
        host=host,
        port=port,
        log_level=log_level,
    )


if __name__ == "__main__":
    goodness()
