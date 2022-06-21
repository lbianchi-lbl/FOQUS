from pathlib import Path
import time
import typing
from PyQt5 import QtWidgets, QtCore

from foqus_lib.gui.uq.uqSetupFrame import uqSetupFrame
from foqus_lib.gui.uq.SimSetup import SimSetup
from foqus_lib.gui.uq.updateUQModelDialog import updateUQModelDialog
from foqus_lib.gui.uq.AnalysisDialog import AnalysisDialog

import pytest


pytestmark = pytest.mark.gui


@pytest.fixture(scope="class", params=["test_files/UQ/Rosenbrock.foqus"])
def session_file_path(examples_dir: Path, request) -> Path:
    return examples_dir / request.param


@pytest.fixture(
    scope="class",
)
def start_uq_session(main_window, session_file_path, qtbot):
    qtbot.focused = main_window
    main_window.loadSessionFile(str(session_file_path), saveCurrent=False)
    main_window.uqSetupAction.trigger()


@pytest.fixture(
    scope="class",
)
def setup_frame(main_window, qtbot) -> uqSetupFrame:
    frame = main_window.uqSetupFrame
    qtbot.focused = frame
    return frame


def _accept_dialog(w):
    import time

    time.sleep(1)
    w.buttonBox.accepted.emit()


class RSCombinations:
    poly_linear = "poly_linear"
    poly_quadratic = "poly_quadratic"


@pytest.mark.usefixtures("start_uq_session")
class TestUQ:
    @pytest.fixture(scope="class")
    def generate_samples(self, qtbot):
        with qtbot.waiting_for_modal(handler=_accept_dialog):
            qtbot.take_screenshot("samples-modal")
            qtbot.click(button="Add New...")
        with qtbot.searching_within(SimSetup) as sim_frame, qtbot.taking_screenshots():
            with qtbot.searching_within(group_box="Choose how to generate samples:"):
                qtbot.click(radio_button="Choose sampling scheme")
            qtbot.select_tab("Distributions")
            qtbot.click(button="All Variable")
            with qtbot.focusing_on(table=any):
                qtbot.select_row(1)
                qtbot.using(column="Type").set_option("Fixed")
            qtbot.select_tab("Sampling scheme")
            qtbot.click(radio_button="All")
            qtbot.using(item_list=any).set_option("Latin Hypercube")
            qtbot.using(spin_box=...).enter_value(2000)
            qtbot.click(button="Generate Samples")
            qtbot.click(button="Done")

    @pytest.fixture(scope="class")
    def simulation_table(self, setup_frame):
        return setup_frame.simulationTable

    def test_generate_samples(self, qtbot, generate_samples, simulation_table):
        assert simulation_table.rowCount() == 1

    @pytest.fixture(scope="class")
    def run_simulation(self, qtbot, simulation_table, setup_frame, timeout_ms=30_000):
        with qtbot.focusing_on(simulation_table):
            qtbot.select_row(0)
            launch_button = qtbot.locate_widget(column="Launch")
            analyze_button = qtbot.locate_widget(column="Analyze")
            with qtbot.waiting_for_modal(timeout=timeout_ms):
                # NOTE: waiting_for_modal() seems to be needed for macOS, or it will hang indefinitely
                launch_button.click()

        def analysis_is_available():
            return analyze_button.isEnabled()

        qtbot.wait_until(analysis_is_available, timeout=timeout_ms)

    @pytest.mark.usefixtures("run_simulation")
    def test_after_running_simulation(self, setup_frame):
        assert len(setup_frame.dat.uqSimList) == 1

    @pytest.fixture(scope="class")
    def analysis_dialog(self, qtbot, setup_frame, simulation_table):
        def has_dialog():
            return setup_frame._analysis_dialog is not None

        with qtbot.focusing_on(simulation_table):
            qtbot.select_row(0)
            qtbot.using(column="Analyze").click()
        qtbot.wait_until(has_dialog, timeout=10_000)

        return setup_frame._analysis_dialog

    def test_analysis_dialog(self, analysis_dialog):
        assert analysis_dialog is not None

    @pytest.fixture(scope="class")
    def setup_analysis_dialog_expert(self, qtbot, analysis_dialog):
        qtbot.focused = frame = analysis_dialog
        qtbot.click(button="Mode: Wizard (Click for Expert Mode)")
        with qtbot.focusing_on(group_box="Analysis"), qtbot.taking_screenshots():
            qtbot.using(combo_box="Select Output under Analysis").set_option(
                "Rosenbrock.f"
            )

    @pytest.fixture(scope="class")
    def run_analyses(self, qtbot, setup_analysis_dialog_expert):
        with qtbot.focusing_on(
            group_box="Ensemble Data Analysis"
        ), qtbot.taking_screenshots():
            # ana_label = "Choose UQ Analysis:"
            type_combo, order_combo = qtbot.locate(
                combo_box="Choose UQ Analysis:", index=[0, 1]
            )

            def run_and_wait():
                qtbot.click(button="Analyze")
                qtbot.wait_until_called(frame.unfreeze)

            run_and_wait()
            qtbot.using(type_combo).set_option("Correlation Analysis")
            run_and_wait()
            qtbot.using(type_combo).set_option("Sensitivity Analysis ->")
            qtbot.using(order_combo).set_option("First-order")
            run_and_wait()
            qtbot.using(order_combo).set_option("Second-order")
            run_and_wait()
        # qtbot.wait(10_000)

    @pytest.mark.usefixtures("run_analyses")
    @pytest.mark.skip
    def test_analyses_performed(self, qtbot):
        with qtbot.searching_within(group_box="Analyses Performed"):
            ana_table = qtbot.locate_widget(table=True)
            assert ana_table.rowCount() > 0

    @pytest.fixture(scope="class")
    def visualize(self, qtbot, setup_analysis_dialog_expert):
        with qtbot.focusing_on(
            group_box="Ensemble Data Analysis"
        ), qtbot.taking_screenshots():
            viz_1st_combo, viz_2nd_combo = qtbot.locate(
                combo_box="Visualize Data:", index=[0, 1]
            )
            viz_button = qtbot.locate(button="Visualize")

            qtbot.using(viz_1st_combo).set_option("Rosenbrock.x4")
            qtbot.click(viz_button)
            qtbot.using(viz_1st_combo).set_option("None selected")
            qtbot.using(viz_2nd_combo).set_option("Rosenbrock.x3")
            qtbot.click(viz_button)
            qtbot.using(viz_1st_combo).set_option("Rosenbrock.x1")
            qtbot.using(viz_2nd_combo).set_option("Rosenbrock.x5")
            qtbot.click(viz_button)

    @pytest.mark.usefixtures("visualize")
    def test_visualization(self, qtbot):
        assert True

    @pytest.fixture(
        scope="function",
        params=[
            "MARS Ranking",
            "Sum of Trees",
            # 'Delta Test',  # takes a long time but eventually finishes
            # 'Gaussian Process'  # doesn't seem to finish even after a long time
        ],
    )
    def input_importance_method(self, request):
        return request.param

    @pytest.fixture(scope="function")
    def calculate_input_importance(
        self, qtbot, setup_analysis_dialog_expert, input_importance_method
    ):
        with qtbot.focusing_on(
            group_box="Qualitative Parameter Selection"
        ), qtbot.taking_screenshots():
            combo = qtbot.locate(combo_box=any)
            button = qtbot.locate(button=any)
            qtbot.using(combo).set_option(input_importance_method)
            qtbot.click(button)

    @pytest.mark.usefixtures("calculate_input_importance")
    def test_input_importance(self):
        assert True

    @pytest.fixture(
        scope="function",
        params=[
            ("Polynomial ->", "Linear Regression"),
            # ('Polynomial ->', 'Quadratic Regression'),
            # ('Polynomial ->', 'Cubic Regression'),
            # ('Polynomial ->', 'Legendre Polynomial Regression'),
            ("MARS ->", None),
            # ('MARS ->', 'MARS with Bagging'),  # this takes a while but eventually converges
            # ('Kriging', None),  # this doesn't seem to converge
            # ('Sum of Trees', None),
            # ('Radial Basis Function', None)  # also takes a looong time
        ],
    )
    def rs_combo_values(self, request):
        return request.param

    @pytest.fixture(scope="function")
    def run_rs_validation(self, qtbot, setup_analysis_dialog_expert, rs_combo_values):
        with qtbot.focusing_on(
            group_box="Response Surface (RS) Based Analysis"
        ), qtbot.taking_screenshots():
            rs_type, rs_subtype = rs_combo_values
            if rs_type:
                qtbot.using(combo_box="Select RS:", index=0).set_option(rs_type)
            if rs_subtype:
                qtbot.using(combo_box="Select RS:", index=1).set_option(rs_subtype)
            qtbot.click(button="Validate")

    @pytest.mark.usefixtures("run_rs_validation")
    def test_rs_validation(self):
        assert True
