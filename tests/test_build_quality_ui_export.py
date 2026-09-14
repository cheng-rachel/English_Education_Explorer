"""Build-only decision UI, legacy restoration, provenance and Markdown checks."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / '03app'))

from streamlit.testing.v1 import AppTest
from solution_export import export_markdown, to_markdown


def record_fixture():
    sources = [
        {'id': 'E1', 'title': '官方互动工具', 'source_type': '产品 / 机构官网',
         'url': 'https://official.example.com/tool?utm_source=test#:\u007e:text=long',
         'content': '这份资料介绍图片提示与英语互动功能。微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com'},
        {'id': 'E2', 'title': '原始学习资料', 'source_type': '研究论文',
         'original_path': '01data/01raw/03learnpath/private.pdf', 'content': '\ufffd\ufffd\ufffd| A | 17 | 2 | 7 |'}]
    brief = {'source_type': 'market_insight', 'target_user': '6–8岁儿童及家长', 'age_range': [72, 107],
             'skills': ['口语表达'], 'contexts': ['家庭固定学习'], 'region': '中国大陆',
             'core_need': '孩子主要用单词和短语回答，希望提升完整句表达。',
             'evidence_sources': deepcopy(sources),
             'source_context': {'analyst': {'hypothesis': '句子组织支持可能值得验证'},
                                'chat': [{'question': '这是假设吗', 'answer': '需要观察实际练习'}]}}
    solution = {
        'solution_scope': 'activity',
        'product_judgment': {'recommendation': '先做一个教学活动，不建议立即开发独立产品。',
                            'reasons': ['一次提示撤除练习即可验证。', '尚不清楚真实表达瓶颈。'], 'evidence_ids': []},
        'opportunity': {'problem_to_solve': brief['core_need'], 'reported_facts': ['用户描述孩子主要以单词和短语回答。'],
                        'unknowns': ['句子组织、词汇调用和提示依赖分别起多大作用？']},
        'product_concept': {'name': '少一点提示', 'target_user': brief['target_user'], 'core_problem': brief['core_need'],
                            'core_mechanism': 'Prompt Fading｜逐步撤除提示', 'value_proposition': '先验证能否迁移到新图片', 'core_scenario': '家庭阅读后'},
        'opportunity_gap': {'existing_strength': '已有图文互动支持', 'remaining_friction': '没有直接使用阻力记录',
                            'opportunity': '逐步减少提示是待验证机会假设', 'status': 'hypothesis', 'evidence_ids': []},
        'teaching_goal': {'learning_outcome': '换一张图片后独立表达完整意思', 'behavior_change': '减少依赖成人完整示范'},
        'solution_mechanism': {'steps': ['完整示范', '关键词提示', '开放问题', '换图独立表达'],
                              'why_it_might_work': '逐步撤除提示，观察能否迁移；尚需实际检验。', 'assumptions': ['孩子愿意参与']},
        'core_interaction': '熟悉图片 → 一个开放问题 → 两级提示 → 换图独立表达',
        'carrier': {'choices': ['纸质书', '家长陪伴'], 'rationale': '已有图片和成人记录即可测试，无需专用硬件。'},
        'ai_role': ['生成一个图片问题'], 'human_role': ['观察并记录所需提示'],
        'mvp': {'core_features': [{'name': '一个图片问题', 'why_essential': '观察独立表达'}, {'name': '两级提示和一次记录', 'why_essential': '检验提示依赖'}],
                'key_pages': [{'name': '一张任务卡', 'purpose': '展示一个问题并记录结果'}], 'minimal_data': ['年龄', '图片', '提示次数'],
                'minimal_ai_capability': ['可选的一个问题生成'], 'not_now': ['自动语音评分', '教师后台', '硬件']},
        'fast_prototype': {'approach': '一张任务卡 + 一个可选 Prompt。', 'copyable_prompt': '请按图片给一个问题。\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com\n返回 {"question": "..."}'},
        'demo_build_path': [{'step': 1, 'title': '准备任务卡', 'action': '挑选两张同难度图片', 'deliverable': '两张图片及记录格'}],
        'validation_metrics': {key: {'metric': metric, 'how_to_measure': '人工记录同难度任务表现'} for key, metric in
                               [('learning', '新图片独立完整表达次数'), ('behavior', '一周完成次数'), ('product', '成人准备时间')]},
        'validation_plan': {'sample': '先找3个家庭', 'duration': '一周', 'comparison': '比较两张同难度图片的提示次数',
                            'decision_criteria': ['先观察再决定']},
        'validation_decision': {'continue': '新情境表达改善且负担可接受时继续。', 'adjust': '仅原图改善时调整迁移任务。',
                                'stop': '没有真实困难或活动已足够解决时停止独立产品化。'},
        'solution_landscape': [{'mechanism': 'AI口语', 'what_exists': '产品自述提供图片互动', 'what_remains_unresolved': '是否减少提示依赖尚待验证', 'evidence_ids': ['E1']}],
        'risks': [{'risk': value, 'cheap_test': '用一次短练习观察'} for value in ['需求可能不真实', '机制可能无效', '成人准备负担']],
        'evidence_ids': ['E1'],
    }
    return {'kind': 'product_concept', 'entry_type': 'build_solution', 'solution': solution, 'opportunity_brief': brief,
            'evidence_sources': sources, 'generated_at': '2026-09-14T15:00:00+08:00',
            'analysis_meta': {'mode': 'demo', 'provider': 'Demo', 'revision_history': []}}


def visible(app):
    return '\n'.join(str(item.value) for kind in ('markdown', 'caption', 'warning', 'info', 'code') for item in app.get(kind))


class BuildQualityUIExport(unittest.TestCase):
    def app(self, record):
        script = 'import streamlit as st\nfrom solution_session import render_product_concept\nrender_product_concept(st.session_state["record"])'
        app = AppTest.from_string(script, default_timeout=20)
        app.session_state['record'] = deepcopy(record)
        with patch('llm.provider.complete_json') as llm, patch('knowledge.retrieval.get_retriever') as retrieve:
            app.run()
        llm.assert_not_called()
        retrieve.assert_not_called()
        self.assertFalse(app.exception)
        return app

    def test_five_sections_and_secondary_content_are_collapsed(self):
        app = self.app(record_fixture())
        text = visible(app)
        for heading in ('① 产品判断', '② Opportunity', '③ 核心机制', '④ MVP', '⑤ Validation'):
            self.assertIn(heading, text)
        self.assertIn('不建议立即开发独立产品', text)
        self.assertIn('尚非独立核验', text)
        self.assertIn('Continue · 继续', text)
        self.assertIn('Adjust · 调整', text)
        self.assertIn('Stop · 停止产品化', text)
        self.assertFalse(app.warning)
        expected = ('Later', '查看快速原型方案', '查看 / 复制 Prompt', 'Solution Landscape', '参考资料', 'Demo Build Path', 'Risks')
        for label in expected:
            expanders = [item for item in app.expander if label in item.label]
            self.assertTrue(expanders, label)
            self.assertTrue(all(not item.proto.expanded for item in expanders), label)
        prompt = next(item for item in app.expander if item.label == '查看 / 复制 Prompt')
        self.assertEqual(len(prompt.get('code')), 1)

    def test_evidence_keeps_official_short_links_and_hides_noise_paths_contacts(self):
        app = self.app(record_fixture())
        text = visible(app)
        self.assertIn('[查看官网](<https://official.example.com/tool>)', text)
        self.assertIn('本地资料', text)
        for hidden in ('abc_teacher123', '13812345678', 'teacher@example.com', '01data/01raw', 'utm_source', '\ufffd\ufffd\ufffd'):
            self.assertNotIn(hidden, text)
        self.assertNotRegex(text, r'\[https?://')
        self.assertIn('尚未用于支持具体方案判断', text)
        self.assertNotIn('Market Evidence', text)

    def test_legacy_history_renders_missing_judgment_without_generation(self):
        record = record_fixture()
        for key in ('solution_scope', 'product_judgment', 'opportunity', 'core_interaction', 'validation_decision'):
            record['solution'].pop(key)
        app = self.app(record)
        text = visible(app)
        self.assertIn('尚未判断', text)
        self.assertIn('这份历史方案尚未记录产品化判断', text)
        self.assertIn('这份历史方案尚未单独记录该条件', text)
        self.assertEqual(app.session_state['record'], record)

    def test_history_preserves_full_result_and_does_not_search_on_restore(self):
        from db import init_db, list_research_sessions
        from output_safety import sanitize_data
        from solution_session import restore_state
        record = record_fixture()
        with tempfile.TemporaryDirectory(prefix='build-quality-history-') as temp:
            with patch.dict(os.environ, {'ENGEDUSCOPE_DB_PATH': str(Path(temp) / 'history.db')}):
                init_db()
                app = AppTest.from_string('import streamlit as st\nfrom solution_session import save_product_concept\nif st.button("save"):\n    save_product_concept(st.session_state["record"])')
                app.session_state['record'] = record
                app.run()
                app.button[0].click().run()
                self.assertFalse(app.exception)
                row = list_research_sessions()[0]
                saved = json.loads(row['summary_json'])
                self.assertEqual(saved, sanitize_data(record))
                with patch('llm.provider.complete_json') as llm, patch('knowledge.retrieval.get_retriever') as retrieve, patch('web_search.provider.search_web') as search:
                    state = restore_state(saved, row['id'])
                llm.assert_not_called()
                retrieve.assert_not_called()
                search.assert_not_called()
                self.assertEqual(state['bs_result'], saved)
                self.assertEqual(saved['solution']['solution_scope'], 'activity')
                self.assertEqual(saved['opportunity_brief']['source_context']['analyst']['hypothesis'], '句子组织支持可能值得验证')

    def test_markdown_order_complete_content_safety_and_non_destructive_export(self):
        record = record_fixture()
        record['analysis_meta']['api_key'] = 'secret-not-exported'
        text = to_markdown(record)
        sections = re.findall(r'^## (.+)$', text, re.M)
        expected = ['Product Judgment', 'Opportunity', 'Core Mechanism', 'MVP', 'Validation', 'Solution Landscape', 'Evidence', 'Demo Build Path', 'Risks']
        self.assertEqual([heading.split('｜')[0] for heading in sections[:9]], expected)
        for value in ('Prompt Fading', 'Teaching Goal', 'Carrier', 'AI Role', 'Human Role', '教师后台', '成人准备负担', '句子组织支持可能值得验证', '这是假设吗', '请按图片给一个问题', '官方互动工具'):
            self.assertIn(value, text)
        for hidden in ('abc_teacher123', '13812345678', 'teacher@example.com', 'secret-not-exported', 'api_key'):
            self.assertNotIn(hidden, text)
        self.assertIn('https://official.example.com', text)
        with tempfile.TemporaryDirectory(prefix='build-quality-export-') as temp:
            output = export_markdown(record, temp)
            initial = output.read_bytes()
            self.assertEqual(export_markdown(record, temp), output)
            record['solution']['product_concept']['name'] += '调整版'
            other = export_markdown(record, temp)
            self.assertNotEqual(other, output)
            self.assertEqual(output.read_bytes(), initial)


if __name__ == '__main__':
    unittest.main()
