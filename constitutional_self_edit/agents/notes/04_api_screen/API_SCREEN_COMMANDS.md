# Reproducing the API editing screen

Run these commands from `constitutional_self_edit/`. The review runner uses Python's standard library and the existing project modules. Analysis plotting additionally needs Matplotlib and NumPy; checks use pytest.

All completed inputs and responses live under `runs/api-screen-20260924/`, which is private and excluded from Git. The frozen plans live in `configs/api-screen-20260924/`. The key is read from `OPENROUTER_API_KEY` or the private file `~/.config/value-drift/openrouter.env`; never place a key in a plan or source file.

Rebuild the saved results and constitution index without making API calls:

```bash
python agents/scripts/analyze_api_screen.py
python agents/scripts/plot_api_screen.py
python -m pytest tests/test_api_screen.py -q
```

Plotting explicitly loads regular, semibold, and bold Myriad Pro from `~/Library/Fonts`. The outputs are eight PNG/PDF/SVG figures and `plot_data.json` under `reports/04_api_screen/figures/`. The analysis joins all three blinded coding passes, checks no moral score, and retains individual codes under `runs/api-screen-20260924/analysis/`.

The original dispatch command for a frozen batch was:

```bash
python agents/scripts/run_api_screen.py --plan configs/api-screen-20260924/batch01.json --workers 3
```

This is a paid command if planned outcomes are missing. Existing completed reviews are read rather than regenerated. All batches use the same ledger and a $28 cumulative reservation guard within this round's $30 authorization. Unknown charges remain reserved; requests are not automatically retried. Do not delete the ledger or use a new root to bypass cumulative spending. A new experiment should have an explicitly new label and budget scope.

Continuation batches require their original parent submissions and original starting document. They preserve the same model/settings, carry only the constitution into a fresh conversation, and stop at the first explicit unchanged submission. The report's full-chain distances include the original parent review even when subsequent reviews live in a separately labeled continuation directory.

The current round is complete. Running the analysis commands is sufficient to regenerate its report figures; no additional inference or training is needed.
