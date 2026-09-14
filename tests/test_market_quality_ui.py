"""Targeted Market presentation checks; no model, network or persistence calls."""
from copy import deepcopy
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '03app'))
from streamlit.testing.v1 import AppTest
from market_session import display_text

FILTERS = {'region': '中国大陆', 'time_window': '近90天', 'age_range': [84, 191],
           'skills': ['阅读理解'], 'contexts': ['自主学习'], 'audiences': ['家长']}


def evidence(count=7):
    values = []
    for index in range(count):
        values.append({'id': f'E{index + 1}', 'title': f'阅读理解产品资料 {index + 1}',
                       'region': '中国大陆', 'source_type': '产品 / 机构官网', 'date': '2026-09-01',
                       'time_scope': 'within_window', 'content_kind': 'local_chunk',
                       'url': f'https://example.org/reading/{index + 1}?id={index + 1}&utm_source=demo#:~:text=reading',
                       'content': f'第{index + 1}种英语阅读理解方案，通过分级阅读与问题反馈支持理解文章。' + '学习者先阅读短文，再说明人物行动与原因。' * 30})
    return values


def record():
    sources = evidence(2)
    signal = {'id': 'saved_signal', 'signal_title': '阅读理解需求正在上升', 'region': '中国大陆',
              'age_range': [84, 191], 'skills': ['阅读理解'], 'contexts': ['自主学习'], 'audiences': ['家长'],
              'trend': '上升', 'trend_basis': '官网数量增加。', 'trend_evidence_ids': ['E1', 'E2'],
              'demand_level': '高', 'signal_status': '新兴', 'evidence_ids': ['E1', 'E2'],
              'problem_summary': '家长普遍不满意现有阅读产品。' * 30,
              'existing_solutions': [{'mechanism': '分级阅读', 'summary': '按难度提供阅读输入与练习。', 'examples': [], 'evidence_ids': ['E1']}],
              'attempted_solutions': [{'description': '家长都试过分级阅读', 'evidence_ids': ['E1']}],
              'dissatisfaction': [{'description': '产品普遍没有效果', 'evidence_ids': ['E1']}],
              'unmet_need': '家长都需要新产品。', 'opportunity_hypothesis': '推出更多产品。',
              'china_observation': '同上。', 'overseas_observation': '',
              'analyst': {'evidence': [{'statement': '家长都不满意。', 'evidence_ids': ['E1']}],
                          'interpretation': '用户越来越焦虑。', 'hypothesis': '应立即推出新产品。'},
              'evidence_sources': sources}
    return {'kind': 'market_research', 'region': '中国大陆', 'filters': FILTERS,
            'time_window': '近90天', 'generated_at': '2026-09-13T12:00:00',
            'signals': [signal], 'evidence_sources': sources, 'analysis_meta': {'mode': 'local_evidence'},
            'search_meta': {'status': 'not_configured'}, 'chat': {}}


def visible(app):
    return '\n'.join(str(item.value) for kind in ('markdown', 'caption', 'info', 'warning', 'error', 'success', 'subheader') for item in app.get(kind))


class MarketQualityUIChecks(unittest.TestCase):
    def render(self, script, fixture):
        app = AppTest.from_string('import sys\n' + f'sys.path.insert(0, {str(ROOT / "03app")!r})\n' +
                                 'import streamlit as st\n' + script, default_timeout=15)
        app.session_state['fixture'] = deepcopy(fixture)
        with patch('requests.get', side_effect=AssertionError('render must not fetch')), \
                patch('requests.post', side_effect=AssertionError('render must not call AI')):
            app.run()
        self.assertFalse(app.exception, [item.message for item in app.exception])
        return app

    def test_sources_folded_short_deduplicated_and_clean_links(self):
        sources = evidence()
        sources.append(dict(sources[0], id='E_duplicate'))
        app = self.render('from market_session import render_market_sources\nrender_market_sources(st.session_state["fixture"], market_context=True)', sources)
        self.assertEqual(app.expander[0].label, '参考资料（7）')
        self.assertTrue(all(not item.proto.expanded for item in app.expander))
        self.assertIn('查看全部资料（7）', [item.label for item in app.expander])
        output = visible(app)
        self.assertNotIn('E_duplicate', output)
        self.assertNotIn('utm_source', output)
        self.assertNotIn(':~:text=', output)
        self.assertIn('[查看官网](<https://example.org/reading/1?id=1>)', output)
        self.assertNotIn('https://', re.sub(r'\[[^\]]+\]\(<[^>]+>\)', '', output))
        excerpts = [item for item in app.expander if item.label == '查看引用片段']
        self.assertTrue(excerpts)
        self.assertTrue(all(len(item.markdown[0].value) <= 140 for item in excerpts))
        # Five source headings sit outside the additional-sources expander.
        additional = next(item for item in app.expander if item.label == '查看全部资料（7）')
        self.assertEqual(sum(item.value.startswith('**E') for item in additional.markdown), 2)
        self.assertEqual(sum(item.value.startswith('**E') for item in app.markdown), 7)

    def test_ocr_private_contacts_and_local_paths_do_not_surface(self):
        sources = evidence(1)
        sources[0]['content'] = '英语阅读理解通过短文复述观察。\n微信：abc_teacher123\n手机：13812345678\n邮箱：teacher@example.com'
        sources.append({'id': 'OCR', 'title': '破损 PDF', 'region': '中国大陆', 'source_type': '行业报告',
                        'content': '英\n语\n阅\n读\n理\n解\n' * 20 + '�' * 10})
        sources.append({'id': 'L1', 'title': '学习路径参考', 'region': 'general_reference', 'raw_category': 'learnpath',
                        'source_type': '通用学习路径参考资料', 'original_path': '01data/01raw/03learnpath/private.pdf',
                        'content': '英语阅读理解需要把词汇识别与文章意义联系起来。'})
        app = self.render('from market_session import render_market_sources\nrender_market_sources(st.session_state["fixture"], market_context=True)', sources)
        output = visible(app)
        for value in ('abc_teacher123', '13812345678', 'teacher@example.com', '�', '01data/', '**OCR'):
            self.assertNotIn(value, output)
        self.assertIn('学习参考', output)
        self.assertIn('本地资料', output)
        self.assertIn('https://example.org/reading/1?id=1', output)

    def test_saved_supply_claims_become_short_observation_without_api(self):
        original = record()
        app = self.render('from market_session import render_market_research\nrender_market_research(st.session_state["fixture"])', original)
        output = visible(app)
        self.assertIn('当前判断', output)
        self.assertIn('真实用户需求证据', output)
        self.assertIn('目前缺少足够真实用户使用记录。', output)
        self.assertIn('当前仅基于本地资料分析。', output)
        self.assertNotIn('阅读理解需求正在上升', output)
        self.assertNotIn('家长都试过分级阅读', output)
        self.assertNotIn('用户越来越焦虑', output)
        self.assertIn('需求程度：证据不足', output)
        self.assertEqual(len([item for item in app.expander if item.label.startswith('参考资料（')]), 1)
        self.assertEqual(original['signals'][0]['trend'], '上升')  # Saved snapshot stays unchanged.

    def test_history_uses_supply_omitted_from_signal_snapshot(self):
        fixture = record()
        fixture['signals'][0]['evidence_sources'] = fixture['evidence_sources'][:1]
        fixture['signals'][0]['evidence_ids'] = ['E1']
        fixture['evidence_sources'][1]['content'] = '英语阅读理解工具通过划线标注呈现文本中的信息线索。'
        app = self.render('from market_session import render_market_research\nrender_market_research(st.session_state["fixture"])', fixture)
        self.assertIn('划线标注', visible(app))

    def test_analyst_chat_short_links_and_existing_actions(self):
        fixture = record()
        fixture['chat'] = {'saved_signal': [{'question': '这个来源靠谱吗 https://example.org/detail?utm_source=chat',
                                           'answer': {'evidence': [], 'interpretation': '可核对 https://example.org/detail?utm_medium=chat。微信：abc_teacher123',
                                                      'hypothesis': '先比较任务完成情况。'}, 'generated_at': '2026-09-13T12:00:00'}]}
        script = ('from market_session import render_market_research\n'
                  'def actions(signal, research, key):\n'
                  '    st.button("继续追问", key="test_chat_" + signal["id"])\n'
                  '    st.button("基于这个需求 Build a Solution", key="test_build_" + signal["id"])\n'
                  'render_market_research(st.session_state["fixture"], actions=actions)')
        app = self.render(script, fixture)
        output = visible(app)
        self.assertIn('追问 1', output)
        self.assertIn('[查看原文](<https://example.org/detail>)', output)
        self.assertNotIn('abc_teacher123', output)
        self.assertNotIn('utm_source', output)
        self.assertTrue(app.button(key='test_chat_saved_signal'))
        self.assertTrue(app.button(key='test_build_saved_signal'))
        self.assertEqual(display_text('[https://example.org/test](https://example.org/test?utm_campaign=x)'), '[查看原文](<https://example.org/test>)')
        self.assertEqual(display_text('[来源](<https://example.org/test?utm_campaign=x>)'), '[查看原文](<https://example.org/test>)')


if __name__ == '__main__':
    unittest.main()
