import logging
import os
import aiohttp

NEIRO_API_URL = os.getenv("NEIRO_API_URL", "http://localhost:8000/predict")

async def get_press_prediction(raw_sets):
    """
    Формирует последовательность признаков и отправляет её на Neiro API (LSTM).
    
    :param raw_sets: список выполненных подходов (объекты Set)
    :return: dict | None
    """
    try:
        sets_sorted = sorted(raw_sets, key=lambda s: s.updated)
        
        if len(sets_sorted) > 5:
            sets_sorted = sets_sorted[-5:]

        sequence = []
        for i, s in enumerate(sets_sorted):
            if i == 0:
                delta_w, delta_r = 0, 0
            else:
                prev = sets_sorted[i - 1]
                delta_w = s.weight - prev.weight
                delta_r = s.repetitions - prev.repetitions

            volume = s.weight * s.repetitions
            sequence.append([
                float(s.weight),
                int(s.repetitions),
                float(volume),
                float(delta_w),
                float(delta_r)
            ])

        while len(sequence) < 5:
            sequence.insert(0, [0, 0, 0, 0, 0])

        logging.info(f"AI input sequence: {sequence}")

        async with aiohttp.ClientSession() as session:
            async with session.post(NEIRO_API_URL, json={"sequence": sequence}, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logging.info(f"Neiro API response: {data}")
                    return data
                else:
                    text = await resp.text()
                    logging.warning(f"Neiro API error {resp.status}: {text}")
                    return None

    except Exception as e:
        logging.exception(f"Exception while calling Neiro API: {e}")
        return None
