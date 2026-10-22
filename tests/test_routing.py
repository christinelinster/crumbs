import importlib
import importlib.util
import unittest


class RoutingToolTests(unittest.TestCase):
    def routing_tools(self):
        spec = importlib.util.find_spec("app.rag.tools")
        self.assertIsNotNone(spec, "app.rag.tools has not been implemented")
        if spec is None:
            return None
        return importlib.import_module("app.rag.tools")

    def test_tool_contract_exposes_only_the_two_read_tools(self):
        tools = self.routing_tools()
        if tools is None:
            return
        schemas = getattr(tools, "RECIPE_TOOLS", None)
        self.assertIsNotNone(schemas)
        if schemas is None:
            return

        self.assertEqual(
            [item["name"] for item in schemas],
            ["get_recipe_detail", "get_recipes"],
        )
        self.assertTrue(all(item["type"] == "function" for item in schemas))
        self.assertTrue(all(item["strict"] is False for item in schemas))
        detail_schema = schemas[0]["parameters"]
        self.assertEqual(detail_schema["required"], ["slug"])
        self.assertFalse(detail_schema["additionalProperties"])
        search_schema = schemas[1]["parameters"]
        self.assertEqual(search_schema["required"], ["input"])
        self.assertEqual(
            set(search_schema["properties"]),
            {"input", "limit", "similar_to_slug"},
        )
        self.assertFalse(search_schema["additionalProperties"])

    def test_zep_schema_exposes_only_supported_search_arguments(self):
        tools = self.routing_tools()
        schemas = tools.get_recipe_tools("zep")
        self.assertEqual(set(schemas[1]["parameters"]["properties"]), {"input", "include_history"})
        self.assertEqual(schemas[1]["parameters"]["required"], ["input"])
        self.assertEqual(set(tools.get_recipe_tools("vector")[1]["parameters"]["properties"]),
                         {"input", "limit", "similar_to_slug"})
