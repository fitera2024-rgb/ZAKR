from decimal import Decimal

import pytest

from hierarchy_account_transfer.hierarchy import Hierarchy, HierarchyError
from hierarchy_account_transfer.models import HierarchyNode
from hierarchy_account_transfer.normalization import account_key, money, text_key


def test_normalization_and_decimal():
    assert text_key("  А\u00a0 Б  ") == "а б"
    assert account_key(26.0) == "26"
    assert money("1 234,555") == Decimal("1234.56")


def test_recursive_scope_and_cycle_detection():
    tree = Hierarchy(
        [
            HierarchyNode("R", "R", "ROOT"),
            HierarchyNode("A", "A", "OTHER", "R"),
            HierarchyNode("B", "B", "DEPARTMENT", "A"),
        ]
    )
    assert tree.scope("R") == {"R", "A", "B"}
    with pytest.raises(HierarchyError, match="BLOCKED_HIERARCHY_CYCLE"):
        Hierarchy([HierarchyNode("A", "A", "OTHER", "B"), HierarchyNode("B", "B", "OTHER", "A")])
