from collections import defaultdict, deque

from .models import HierarchyNode


class HierarchyError(ValueError):
    pass


class Hierarchy:
    def __init__(self, nodes: list[HierarchyNode]):
        self.nodes: dict[str, HierarchyNode] = {}
        for node in nodes:
            if not node.code or node.code in self.nodes:
                raise HierarchyError("BLOCKED_DUPLICATE_NODE_CODE")
            self.nodes[node.code] = node
        self.children: dict[str, list[str]] = defaultdict(list)
        for node in nodes:
            if node.parent_code:
                if node.parent_code not in self.nodes:
                    raise HierarchyError(f"Unknown parent: {node.parent_code}")
                self.children[node.parent_code].append(node.code)
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(code: str) -> None:
            if code in visiting:
                raise HierarchyError("BLOCKED_HIERARCHY_CYCLE")
            if code in visited:
                return
            visiting.add(code)
            for child in self.children[code]:
                visit(child)
            visiting.remove(code)
            visited.add(code)

        for code in sorted(self.nodes):
            visit(code)

    @property
    def roots(self) -> list[HierarchyNode]:
        return sorted(
            (n for n in self.nodes.values() if not n.parent_code and n.node_type == "ROOT"),
            key=lambda n: n.code,
        )

    def scope(self, root_code: str) -> set[str]:
        if root_code not in self.nodes:
            raise HierarchyError("BLOCKED_ROOT_NOT_FOUND")
        result: set[str] = set()
        queue = deque([root_code])
        while queue:
            code = queue.popleft()
            if code in result:
                continue
            result.add(code)
            queue.extend(sorted(self.children[code]))
        root = self.nodes[root_code]
        root_names = {root.code, root.name}
        result.update(n.code for n in self.nodes.values() if n.upper_level in root_names)
        return result

    def validate_analytics(self, organization: str, department: str, scope: set[str]) -> str | None:
        if organization not in self.nodes:
            return "BLOCKED_ORG_NOT_IN_HIERARCHY"
        if department not in self.nodes:
            return "BLOCKED_DEPARTMENT_NOT_IN_HIERARCHY"
        if organization not in scope or department not in scope:
            return "EXCLUDED_OUTSIDE_SELECTED_ROOT"
        owner = self.nodes[department].owner_organization_code
        if owner and owner != organization:
            return "BLOCKED_ORG_DEPT_OWNER_MISMATCH"
        return None
