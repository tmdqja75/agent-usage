from agent_usage.render._counters import OTHER_LABEL, bucket_top_n, rank_usage


def test_rank_usage_orders_by_count_then_name():
    ranked = rank_usage({"b": 1, "a": 3, "c": 3})
    assert ranked == [("a", 3), ("c", 3), ("b", 1)]


def test_bucket_top_n_folds_overflow_into_other():
    ranked = [("a", 5), ("b", 4), ("c", 3), ("d", 2)]
    assert bucket_top_n(ranked, 2) == [("a", 5), ("b", 4), (OTHER_LABEL, 5)]


def test_bucket_top_n_no_overflow_keeps_all():
    ranked = [("a", 5), ("b", 4)]
    assert bucket_top_n(ranked, 2) == [("a", 5), ("b", 4)]
