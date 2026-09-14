"""Focused parent/student readability and saved-result checks, with isolated storage."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / '03app'))

from streamlit.testing.v1 import AppTest
from db import get_research_session, init_db, save_research_session
from need_practice import practical_plan
from need_session import db_entry_type, db_user_type, make_title


def visible(app):
    return '\n'.join(str(item.value) for kind in ('markdown', 'caption', 'warning', 'info', 'error', 'code')
                     for item in app.get(kind))


def fixture(intent='getting_started', *, student=False):
    year = 12 if student else 7 if intent == 'diagnose_bottleneck' else 5 if intent == 'product_choice' else 4
    problem = ('我12岁，英语听力总是听不懂，每天应该怎么练？' if student else
               '7岁，分级阅读读得不错，但是几乎不开口。' if year == 7 else
               '5岁英语启蒙应该选什么类型的产品？' if year == 5 else '孩子4岁，零基础，不知道英语启蒙怎么开始。')
    age = {'mode': 'exact', 'years': year, 'months': 0, 'age_months': year * 12, 'display': f'{year}岁0个月'}
    inputs = {'user_type': 'student' if student else 'parent', 'entry_type': 'student_specific' if student else 'parent_specific',
              'age': age, 'problem': problem, 'skills': ['听力'] if student else ['说'], 'contexts': ['自主学习'], 'methods': []}
    plan = practical_plan(inputs, {'primary_skills': ['听力解码'] if student else ['口语表达'] if year == 7 else ['听力理解']}, intent,
                          user_type=inputs['user_type'])
    result = {**inputs, 'need_intent': {'primary_intent': intent, 'secondary_intents': []},
              'generated_at': '2026-09-16T10:00:00+08:00', 'analysis_meta': {'mode': 'mock'},
              'search_meta': {'status': 'not_configured', 'message': '未启用联网服务，本次使用本地资料。'},
              'need_analysis': {'problem_summary': '先用一个短任务观察独立表现，再决定下一步。', 'primary_skills': ['听力理解'],
                                'possible_causes': [{'cause': '旧版重复原因', 'why': '不应与新版判断重复展示'}],
                                'priority': {'focus_now': ['旧版重复优先级']}, 'next_steps': ['旧版重复下一步']},
              'student_practice_plan' if student else 'parent_action_plan': plan,
              'solution_routes': [{'route_name': '官方儿童英语学习资料', 'mechanism': '分级听读', 'why_it_fits': '能先试听熟悉话题，按理解表现选择难度。',
                                   'recommended_actions': ['同一短材料先试一次，再决定是否保留。'],
                                   'existing_options': [{'name': 'British Council LearnEnglish Kids', 'why_match': '可查看分级故事和互动练习，不能据此保证效果。', 'evidence_ids': ['E1']}]}],
              'ai_diy': {'title': '备用小任务', 'steps': ['选熟悉场景写一句。']},
              'evidence_sources': [{'id': 'E1', 'title': '官方英语练习资料', 'content_role': 'product_info',
                                    'source_type': '产品资料', 'source_url': 'https://learnenglishkids.britishcouncil.org/',
                                    'text': '可以先用熟悉话题试听。微信：private_teacher_88，电话13800138000。' * 10},
                                   {'id': 'E2', 'title': '学习路径参考', 'content_role': 'learning_path', 'source_type': '通用学习路径参考资料',
                                    'original_path': '01data/01raw/03learnpath/private_test.md', 'text': '学习路径用于选择起点。'}]}
    if intent == 'diagnose_bottleneck':
        result['need_reasoning'] = {
            'reported_facts': ['家长描述分级阅读比较顺利，但主动表达很少。'],
            'hypotheses': [{'cause': '可能依赖书中文字提示', 'check': '读后合上书，换一个熟悉图片问同一个意思。', 'if_observed': '有提示会说、撤掉提示卡住时，先逐步减少提示。'},
                           {'cause': '可能缺少真实表达机会', 'check': '给一个需要自己请求的物品，等待一句表达。', 'if_observed': '有真实目的更愿意说时，优先增加短请求机会。'}],
            'to_confirm': ['不看书时，能否先用关键词表达同一意思？']}
    return result


class SolveDeepUITests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='solve-deep-ui-')
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        for patcher in (
            patch.dict(os.environ, {'ENGEDUSCOPE_DB_PATH': str(self.directory / 'history.db'),
                                    'ENGEDUSCOPE_RAW_ROOT': str(self.directory / 'raw'),
                                    'ENGEDUSCOPE_KNOWLEDGE_ROOT': str(self.directory / 'knowledge'),
                                    'ENGEDUSCOPE_LLM_PROVIDER': 'mock'}, clear=True),
            patch('llm.settings.CONFIG_PATH', self.directory / 'llm.json'),
            patch('web_search.settings.CONFIG_PATH', self.directory / 'search.json'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        init_db()

    def render(self, result):
        app = AppTest.from_string("from need_session import render_analysis_result\nimport streamlit as st\nrender_analysis_result(st.session_state['fixture'])")
        app.session_state['fixture'] = deepcopy(result)
        app.run()
        self.assertFalse(app.exception)
        return app

    def expander(self, app, label):
        return next(item for item in app.expander if item.label == label)

    def test_parent_starting_plan_has_stages_and_keeps_options_and_references_closed(self):
        result = fixture()
        app = self.render(result)
        text = visible(app)
        for part in ('当前判断', '先解决什么', '每天具体做什么', '前2–4周', '4–8周', '什么时候进入下一阶段', '什么时候增加难度', '怎么判断有没有进步'):
            self.assertIn(part, text)
        self.assertFalse(self.expander(app, '其他可选方案').proto.expanded)
        self.assertFalse(self.expander(app, '参考资料（2）').proto.expanded)
        self.assertFalse(self.expander(app, '需要时，用 AI 准备一个小任务').proto.expanded)
        self.assertNotIn('旧版重复优先级', text)
        self.assertNotIn('旧版重复下一步', text)
        self.assertIn('[查看原文](https://learnenglishkids.britishcouncil.org/)', text)
        self.assertNotIn('01data/01raw/', text)
        self.assertNotIn('private_teacher_88', text)
        self.assertNotIn('13800138000', text)
        self.assertTrue(any(button.label == '希望根据需求匹配排序' for button in app.button))
        self.assertEqual(result, fixture())

    def test_parent_bottleneck_displays_facts_checks_before_optional_products(self):
        app = self.render(fixture('diagnose_bottleneck'))
        text = visible(app)
        self.assertTrue(self.expander(app, '最可能卡在哪里 · 先怎么验证').proto.expanded)
        self.assertFalse(self.expander(app, '其他可选方案').proto.expanded)
        for part in ('已知', '可能原因', '先验证', '根据表现再行动', '仍需确认'):
            self.assertIn(part, text)
        self.assertNotIn('旧版重复原因', text)
        self.assertLess(text.index('先验证'), text.index('官方儿童英语学习资料'))

    def test_student_plan_is_direct_and_does_not_render_parent_product_routes(self):
        app = self.render(fixture('skill_practice', student=True))
        text = visible(app)
        for part in ('你现在可能卡在哪里', '今天可以怎么练', '接下来一周怎么安排', '什么时候增加难度', '怎么判断有没有进步', '什么时候建议找老师'):
            self.assertIn(part, text)
        self.assertFalse(self.expander(app, '参考资料（2）').proto.expanded)
        self.assertNotIn('British Council LearnEnglish Kids', text)
        self.assertNotIn('家长参与', text)
        self.assertNotIn('备用小任务', text)

    def test_product_choice_reveals_matching_reasons_without_ranking(self):
        app = self.render(fixture('product_choice'))
        self.assertTrue(self.expander(app, '可以考虑的产品 / 支持方式').proto.expanded)
        self.assertTrue(self.expander(app, '具体怎么做').proto.expanded)
        text = visible(app)
        self.assertIn('不排名', text)
        self.assertIn('不能据此保证效果', text)
        self.assertIn('按理解表现选择难度', text)
        self.assertNotIn('private_teacher_88', text)

    def test_saved_bottleneck_restores_new_structure_without_search_retrieval_or_ai(self):
        result = fixture('diagnose_bottleneck')
        session_id = save_research_session(make_title(result), db_user_type(result), db_entry_type(result), result)
        saved = json.loads(get_research_session(session_id)['summary_json'])
        with patch('need_analysis.analyze_parent', side_effect=AssertionError('No analysis on restore')) as analyze, \
             patch('need_analysis.get_retriever', side_effect=AssertionError('No retrieval on restore')) as retrieve, \
             patch('need_evidence.search_web', side_effect=AssertionError('No search on restore')) as search, \
             patch('llm.provider.complete_json', side_effect=AssertionError('No AI on restore')) as model:
            app = AppTest.from_file(str(PROJECT / '03app' / '00_app.py'), default_timeout=25).run()
            app.switch_page('04_history.py').run()
            app.button(key=f'hist_view_{session_id}').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(self.expander(app, '最可能卡在哪里 · 先怎么验证').proto.expanded)
            self.assertFalse(self.expander(app, '参考资料（2）').proto.expanded)
            app.button(key=f'hist_resume_{session_id}').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['sn_result'], saved)
            self.assertEqual(app.radio(key='sn_identity').value, '我是家长')
            self.assertIn('先验证', visible(app))
            self.assertTrue(any(button.key == 'sn_reanalyze' for button in app.button))
            for spy in (analyze, retrieve, search, model):
                spy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
