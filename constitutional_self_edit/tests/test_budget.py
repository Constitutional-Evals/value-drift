from recursive_oct.budget import estimated_spend, can_afford

def test_closed_and_active_resources_accumulate():
    ledger={'authorized_ceiling_usd':200,'reserve_usd':15,'resources':[
        {'hourly_usd':5,'started_epoch':0,'ended_epoch':3600},
        {'hourly_usd':4,'started_epoch':3600}]}
    assert estimated_spend(ledger,7200)==9
    assert can_afford(ledger,7200,175)
    assert not can_afford(ledger,7200,177)

def test_reserve_is_not_spendable_for_training():
    ledger={'authorized_ceiling_usd':200,'reserve_usd':15,'resources':[],'fixed_cost_usd':180}
    assert can_afford(ledger,0,5)
    assert not can_afford(ledger,0,5.01)

def test_explicitly_removed_ceiling_does_not_stop_training_or_accounting():
    ledger={'authorized_ceiling_usd':None,'reserve_usd':0,
            'resources':[{'hourly_usd':5,'started_epoch':0}], 'fixed_cost_usd':200}
    assert estimated_spend(ledger,7200)==210
    assert can_afford(ledger,7200,1000)
