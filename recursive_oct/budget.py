"""Conservative cumulative cost estimates shared by runner and local watchdog."""

def estimated_spend(ledger, now):
    total = float(ledger.get('fixed_cost_usd', 0))
    for resource in ledger.get('resources', []):
        end = resource.get('ended_epoch') or now
        total += max(0, end - resource['started_epoch']) / 3600 * resource['hourly_usd']
    return total


def can_afford(ledger, now, projected_usd=0):
    if ledger['authorized_ceiling_usd'] is None:
        return True  # Explicit authorization without a fixed dollar ceiling.
    available = ledger['authorized_ceiling_usd'] - ledger['reserve_usd']
    return estimated_spend(ledger, now) + projected_usd <= available
