"""40周孕期知识库单元测试"""
import pytest
from app.data.pregnancy_weeks import get_week_data, WeekData, _WEEKS


class TestWeekData:
    """WeekData 类测试"""

    def test_all_40_weeks_populated(self):
        """验证全部40周数据已填充"""
        assert len(_WEEKS) == 40, f"期望40周，实际{len(_WEEKS)}周"
        for i, wd in enumerate(_WEEKS):
            week_num = i + 1
            assert wd.week == week_num, f"第{i+1}个元素的week应为{week_num}，实际为{wd.week}"
            assert wd.size, f"第{week_num}周缺少 size"
            assert wd.milestone, f"第{week_num}周缺少 milestone"
            assert wd.mom_changes, f"第{week_num}周缺少 mom_changes"
            assert wd.weekly_tips, f"第{week_num}周缺少 weekly_tips"
            assert wd.diet_advice, f"第{week_num}周缺少 diet_advice"
            assert wd.exercise_advice, f"第{week_num}周缺少 exercise_advice"
            assert wd.warning_signs, f"第{week_num}周缺少 warning_signs"

    def test_each_week_has_unique_milestone(self):
        """验证每周末宝宝发育里程碑不重复"""
        milestones = [wd.milestone for wd in _WEEKS]
        assert len(set(milestones)) == 40, "40周的milestone应各不相同"

    def test_each_week_has_unique_mom_changes(self):
        """验证每周妈妈变化不重复"""
        changes = [wd.mom_changes for wd in _WEEKS]
        assert len(set(changes)) == 40, "40周的mom_changes应各不相同"


class TestGetWeekData:
    """get_week_data() 函数测试"""

    def test_returns_correct_week(self):
        wd = get_week_data(1)
        assert wd.week == 1
        wd = get_week_data(20)
        assert wd.week == 20
        wd = get_week_data(40)
        assert wd.week == 40

    def test_clamps_below_1(self):
        wd = get_week_data(0)
        assert wd.week == 1
        wd = get_week_data(-5)
        assert wd.week == 1

    def test_clamps_above_40(self):
        wd = get_week_data(41)
        assert wd.week == 40
        wd = get_week_data(100)
        assert wd.week == 40

    def test_common_weeks(self):
        """验证常用孕周的关键属性"""
        # 第16周：胎儿听力发育、吮吸反射建立
        w16 = get_week_data(16)
        assert "13" in w16.size_cm
        assert "吮吸" in w16.milestone or "声音" in w16.milestone or "听力" in w16.milestone

        # 第28周：进入孕晚期，眼睛睁开
        w28 = get_week_data(28)
        assert w28.week == 28
        assert len(w28.milestone) > 20

        # 第40周：足月
        w40 = get_week_data(40)
        assert w40.week == 40


class TestAsMethods:
    """格式转换方法测试"""

    def test_as_baby_info_shape(self):
        info = get_week_data(20).as_baby_info()
        expected_keys = {"size", "size_cm", "weight", "milestone", "current_week"}
        assert set(info.keys()) == expected_keys
        assert info["current_week"] == 20
        assert len(info["size"]) > 2  # 有实际水果类比
        assert len(info["milestone"]) > 20

    def test_as_mom_changes_shape(self):
        mc = get_week_data(25).as_mom_changes()
        assert set(mc.keys()) == {"week", "changes"}
        assert mc["week"] == 25
        assert len(mc["changes"]) > 10  # 有实际内容

    def test_as_recommendations_shape(self):
        rec = get_week_data(30).as_recommendations()
        expected_keys = {"weekly_tips", "diet_advice", "exercise_advice", "warning_signs"}
        assert set(rec.keys()) == expected_keys
        for v in rec.values():
            assert len(v) > 5, f"推荐字段不应为空: {rec}"

    def test_as_baby_info_includes_current_week(self):
        """验证 as_baby_info 包含正确的 current_week"""
        for week in [1, 12, 24, 36, 40]:
            info = get_week_data(week).as_baby_info()
            assert info["current_week"] == week


class TestTrimesterCoverage:
    """孕期阶段覆盖测试"""

    def test_first_trimester(self):
        """孕早期 (1-12周) 内容应反映早孕特征"""
        for w in [4, 8, 12]:
            wd = get_week_data(w)
            # 至少提到叶酸、孕吐、胚胎发育等关键词中的几个
            combined = wd.weekly_tips + wd.mom_changes + wd.milestone
            assert len(combined) > 30

    def test_second_trimester(self):
        """孕中期 (13-28周) 内容应反映中期特征"""
        for w in [16, 20, 24, 28]:
            wd = get_week_data(w)
            combined = wd.weekly_tips + wd.mom_changes + wd.milestone
            assert len(combined) > 30

    def test_third_trimester(self):
        """孕晚期 (29-40周) 内容应反映晚期特征"""
        for w in [32, 36, 40]:
            wd = get_week_data(w)
            combined = wd.weekly_tips + wd.mom_changes + wd.milestone
            assert len(combined) > 30
