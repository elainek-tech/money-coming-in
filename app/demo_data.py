"""Fictional sample data for a made-up home-renovation company. No real people or clients."""

# Single messages, each sent from a different sender. Each tests one behaviour.
SINGLE_MESSAGES = [
    "We're redoing our 3-bedroom flat in June, budget around RM80k, I'm signing off. Can someone call me this week?",
    "How much is a kitchen renovation? Just comparing prices for my parents.",
    "Boss wants 3 quotes for our office fit-out by Friday. Budget TBC.",
    "Boleh quote untuk cat rumah? Nak siap before Raya, budget dalam RM5k.",
    "CONGRATULATIONS! You won a free cruise, click here now.",
    "The tap is still leaking after your plumber came on Monday.",
]

# One conversation, sent one message at a time, to watch a lead warm up.
CONVERSATION = [
    "Hi, do you do kitchen renovations?",
    "We just got the keys to a 3-bedroom flat and want it ready by January.",
    "Budget is around RM60k. My husband and I are deciding together.",
]

# A dormant lead is seeded before the talk, then this message arrives from the same account.
DORMANT_OLD_MESSAGES = [
    "We want to renovate the whole terrace house.",
    "RM15k is all we have, so probably not for now. Thanks anyway.",
]
RECYCLE_MESSAGE = "We got a bonus, budget is now RM45k. Can you quote the living room and kitchen?"
