"""Cards follow the answer's selected recipe identities, not retrieval count."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.rag.query import process_query_result


class RecipeCardSelectionTests(unittest.TestCase):
    def run_answer(self, backend, selected_slugs):
        cards = [{'slug': f'recipe-{i}', 'title': f'Recipe {i}'} for i in range(8)]
        call = SimpleNamespace(type='function_call', name='get_recipes', call_id='search-1')
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output=[call], output_text='')
        client.responses.parse.return_value = SimpleNamespace(output_parsed=SimpleNamespace(
            answer='The selected recipe recommendations.', recipe_slugs=selected_slugs,
        ))
        tool_result = {'tool_name': 'get_recipes', 'retrieval_backend': backend, 'matches': []}
        with patch('app.rag.query.OpenAI', return_value=client), patch(
            'app.rag.query._execute_recipe_tool', return_value=(tool_result, cards),
        ):
            result = process_query_result('Dinner ideas?', [], retrieval_backend=backend)
        return result, client

    def test_card_count_follows_answer_with_one_three_or_six_recipes_in_both_modes(self):
        for backend in ('vector', 'zep'):
            for count in (1, 3, 6):
                with self.subTest(backend=backend, count=count):
                    selected = [f'recipe-{i}' for i in range(count)]
                    result, client = self.run_answer(backend, selected)
                    self.assertEqual([card['slug'] for card in result.recipe_cards], selected)
                    self.assertEqual(result.answer, 'The selected recipe recommendations.')
                    client.responses.create.assert_called_once()
                    client.responses.parse.assert_called_once()

    def test_cards_follow_answer_order_and_exclude_duplicates_and_unknown_slugs(self):
        result, _ = self.run_answer('zep', ['recipe-6', 'recipe-1', 'recipe-6', 'invented'])
        self.assertEqual([card['slug'] for card in result.recipe_cards], ['recipe-6', 'recipe-1'])

    def test_no_recommendations_means_no_cards_even_when_retrieval_found_recipes(self):
        for backend in ('vector', 'zep'):
            with self.subTest(backend=backend):
                result, _ = self.run_answer(backend, [])
                self.assertEqual(result.recipe_cards, [])

    def test_unparsed_answer_does_not_fall_back_to_all_retrieved_cards(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output=[SimpleNamespace(type='function_call', call_id='search-1')])
        client.responses.parse.return_value = SimpleNamespace(output_parsed=None)
        with patch('app.rag.query.OpenAI', return_value=client), patch(
            'app.rag.query._execute_recipe_tool', return_value=({'matches': []}, [{'slug': 'one', 'title': 'One'}]),
        ):
            with self.assertRaises(ValueError):
                process_query_result('Dinner?', [])
