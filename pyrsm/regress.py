import pandas as pd
import statsmodels.formula.api as smf
from typing import Optional
from statsmodels.regression.linear_model import RegressionResults as rrs
from shiny import App
from .radiant.regress import model_regress
from .utils import ifelse, format_nr, setdiff
from .visualize import pred_plot_sm, vimp_plot_sm
from .model import (
    sig_stars,
    model_fit,
    extract_evars,
    extract_rvar,
    scatter_plot,
    reg_dashboard,
    residual_plot,
    coef_plot,
    predict_ci,
)
from .model import vif as calc_vif
from .visualize import distr_plot
from .basics import correlation


class regress:
    def __init__(
        self,
        dataset: pd.DataFrame,
        rvar: Optional[str] = None,
        evar: Optional[list[str]] = None,
        form: Optional[str] = None,
    ) -> None:

        """
        Estimate linear regression model

        Parameters
        ----------
        dataset: pandas DataFrame; dataset
        evar: List of strings; contains the names of the columns of data to be used as explanatory variables
        rvar: String; name of the column to be used as the response variable
        form: String; formula for the regression equation to use if evar and rvar are not provided
        """
        self.dataset = dataset
        self.rvar = rvar
        self.evar = ifelse(isinstance(evar, str), [evar], evar)
        self.form = form

        if self.form:
            self.fitted = smf.ols(formula=self.form, data=self.dataset).fit()
            self.evar = extract_evars(self.fitted.model, self.dataset.columns)
            self.rvar = extract_rvar(self.fitted.model, self.dataset.columns)
        else:
            self.form = f"{self.rvar} ~ {' + '.join(self.evar)}"
            self.fitted = smf.ols(self.form, data=self.dataset).fit()

        df = pd.DataFrame(self.fitted.params, columns=["coefficient"]).dropna()
        df["std.error"] = self.fitted.params / self.fitted.tvalues
        df["t.value"] = self.fitted.tvalues
        df["p.value"] = self.fitted.pvalues
        df["  "] = sig_stars(self.fitted.pvalues)
        self.coef = df.reset_index()

    def summary(self, ssq=False, vif=False, dec=3, name="Not provided") -> None:
        """
        Summarize output from a linear regression model

        parameters
        ----------
        ssq: Boolean; if True, include sum of squares
        vif: Boolean; if True, include variance inflation factors
        """
        print("Linear regression (OLS)")
        print("Data                 :", name)
        print("Response variable    :", self.rvar)
        print("Explanatory variables:", ", ".join(self.evar))
        print(f"Null hyp.: the effect of x on {self.rvar} is zero")
        print(f"Alt. hyp.: the effect of x on {self.rvar} is not zero")

        df = self.coef.copy()
        df["coefficient"] = df["coefficient"].round(2)
        df["std.error"] = df["std.error"].round(dec)
        df["t.value"] = df["t.value"].round(dec)
        df["p.value"] = ifelse(
            df["p.value"] < 0.001, "< .001", df["p.value"].round(dec)
        )
        print(f"\n{df.to_string(index=False)}")
        print("\nSignif. codes:  0 '***' 0.001 '**' 0.01 '*' 0.05 '.' 0.1 ' ' 1")
        print(f"\n{model_fit(self.fitted)}")

        if ssq:
            print("\nSum of squares:")
            index = ["Regression", "Error", "Total"]
            sum_of_squares = [
                self.fitted.ess,
                self.fitted.ssr,
                self.fitted.centered_tss,
            ]
            sum_of_squares = pd.DataFrame(index=index).assign(
                df=format_nr(
                    [
                        self.fitted.df_model,
                        self.fitted.df_resid,
                        self.fitted.df_model + self.fitted.df_resid,
                    ],
                    dec=0,
                ),
                SS=format_nr(sum_of_squares, dec=0),
            )
            print(f"\n{sum_of_squares.to_string()}")

        if vif:
            print("\nVariance inflation factors:")
            print(f"\n{calc_vif(self.fitted).to_string(index=False)}")

    def predict(self, df=None, ci=False, alpha=0.05) -> pd.DataFrame:
        """
        Predict values for a linear regression model
        """
        if df is None:
            df = self.dataset
        df = df.loc[:, self.evar].copy()
        if ci:
            return pd.concat([df, predict_ci(self.fitted, df, alpha=alpha)], axis=1)
        else:
            pred = pd.DataFrame().assign(prediction=self.fitted.predict(df))
            return pd.concat([df, pred], axis=1)

    def plot(
        self,
        plots="dist",
        nobs: int = 1000,
        intercept=False,
        alpha=0.05,
        incl=None,
        excl=[],
        incl_int=[],
        fix=True,
        hline=False,
        figsize=None,
    ) -> None:
        """
        Plots for a linear regression model
        """
        dataset = self.dataset[[self.rvar] + self.evar].copy()
        if "dist" in plots:
            distr_plot(dataset)
        if "corr" in plots:
            cr = correlation(dataset)
            cr.plot(nobs=nobs, figsize=figsize)
        if "scatter" in plots:
            scatter_plot(self.fitted, dataset, nobs=nobs, figsize=figsize)
        if "dashboard" in plots:
            reg_dashboard(self.fitted, nobs=nobs)
        if "residual" in plots:
            residual_plot(self.fitted, dataset, nobs=nobs, figsize=figsize)
        if "pred" in plots:
            pred_plot_sm(
                self.fitted,
                self.dataset,
                incl=incl,
                excl=excl,
                incl_int=incl_int,
                fix=fix,
                hline=hline,
                nnv=20,
                minq=0.025,
                maxq=0.975,
            )
        if "vimp" in plots:
            vimp_plot_sm(self.fitted, self.dataset, rep=10, ax=None, ret=False)
        if "coef" in plots:
            coef_plot(
                self.fitted,
                alpha=alpha,
                intercept=intercept,
                incl=incl,
                excl=excl,
                figsize=figsize,
            )

    def f_test(self, vtt=None, dec=3) -> None:
        """
        F-test for competing models

        Parameters
        ----------
        vtt : list
            List of strings; contains the names of the columns of data to be tested
        """
        if vtt is None:
            form = f"{self.rvar} ~ 1"
            vtt = self.evar.copy()
        else:
            evar = setdiff(self.evar, vtt)
            if len(evar) == 0:
                form = f"{self.rvar} ~ 1"
            else:
                form = f"{self.rvar} ~ {' + '.join(evar)}"

        vtt = ifelse(isinstance(vtt, str), [vtt], vtt)
        hypothesis = [f"({v} = 0)" for v in vtt]
        print(f"Model 1: {form}")
        print(f"Model 2: {self.form}")
        out = self.fitted.f_test(hypothesis)
        pvalue = ifelse(out.pvalue < 0.001, "< .001", round(out.pvalue, dec))
        print(
            f"F-statistic: {round(out.fvalue, dec)} df ({out.df_num:,.0f}, {out.df_denom:,.0f}), p.value {pvalue}"
        )