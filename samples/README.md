# Sample documents

`make_sample.py` generates `electricity_bill.png`, a fake BESCOM electricity
bill used by the **Try sample bill** button and by the test suite.

```bash
python samples/make_sample.py
```

The generated PNG is a 1000×1300 synthetic bill with a payment due date, a late
fee note and a disconnection warning. All names and numbers are fictional. The
image is generated locally; nothing leaves your machine unless you run the live
pipeline.
