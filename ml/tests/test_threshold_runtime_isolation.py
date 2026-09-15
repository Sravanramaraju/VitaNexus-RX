import ast
import inspect
import textwrap

from vitanexus_ml.inference.predictor import Predictor


def test_live_predictor_does_not_consume_offline_binary_threshold():
    tree = ast.parse(textwrap.dedent(inspect.getsource(Predictor.predict)))
    threshold_subscripts = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "threshold"
    ]
    assert threshold_subscripts == []
