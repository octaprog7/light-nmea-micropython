#!/bin/bash
# SPDX-License-Identifier: GPL-3.0

# Автоматически определяю корень проекта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
if [[ "$SCRIPT_DIR" == */tests ]]; then
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi

# Активация виртуального окружения
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

RUNS=10
PAUSE=2
MAIN_SCRIPT="$PROJECT_ROOT/main.py"

if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "ОШИБКА: Файл $MAIN_SCRIPT не найден!"
    exit 1
fi

echo "======================================================================"
echo "МНОГОКРАТНЫЙ ЗАПУСК ТЕСТА ($RUNS прогонов)"
echo "Запускаем: $MAIN_SCRIPT"
echo "======================================================================"
echo ""

printf "%-5s | %-10s | %-10s | %-10s | %-12s\n" \
    "Прогон" "До [КБ]" "После [КБ]" "Дельта" "Скорость"
echo "----------------------------------------------------------------------"

deltas=()
befores=()

for i in $(seq 1 $RUNS); do
    output=$(python3 "$MAIN_SCRIPT" 2>&1)

    # Парсинг данных
    mem_before=$(echo "$output" | grep "Используемая память до теста" | grep -oE '[0-9]+' | tail -1)
    mem_after=$(echo "$output" | grep "Используемая память после теста" | grep -oE '[0-9]+' | tail -1)
    delta=$(echo "$output" | grep "Результат:" | grep -oE '[0-9]+' | tail -1)
    speed=$(echo "$output" | grep "Скорость обработки" | grep -oE '[0-9]+' | tail -1)

    # Проверка знака дельты
    if echo "$output" | grep -q "уменьшилось"; then
        sign="-"
        raw_delta="-$delta"
    else
        sign="+"
        raw_delta="$delta"
    fi

    printf "%-5s | %-10s | %-10s | %s%-9s | %-12s\n" \
        "$i" "${mem_before:-N/A}" "${mem_after:-N/A}" "$sign" "${delta:-N/A}" "${speed:-N/A} п/с"

    deltas+=("${raw_delta:-0}")
    befores+=("${mem_before:-0}")

    if [ $i -lt $RUNS ]; then
        sleep $PAUSE
    fi
done

echo "==============="
echo "АНАЛИЗ ТРЕНДА"
echo "==============="

# Считаю среднюю внутреннюю дельту процесса
sum=0
count=0
for d in "${deltas[@]}"; do
    if [ -n "$d" ] && [ "$d" != "0" ]; then
        sum=$(echo "$sum + $d" | bc)
        count=$((count + 1))
    fi
done

if [ $count -gt 0 ]; then
    avg=$(echo "scale=1; $sum / $count" | bc)
    echo "Среднее потребление функции внутри процесса: $avg КБ"
fi

# Анализ стабильности базовой памяти Python от запуска к запуску
# Исключаю 1-й 'холодный' прогон для правильности оценки (в нем импорты)
sum_base=0
count_base=0
for ((j=1; j<${#befores[@]}; j++)); do
    sum_base=$((sum_base + befores[j]))
    count_base=$((count_base + 1))
done

base_avg=0
if [ $count_base -gt 0 ]; then
    base_avg=$((sum_base / count_base))
fi

echo "Базовый размер Python на старте (со 2-го прогона): $base_avg КБ"

# Проверяю разброс дельт между стабильными прогонами (со 2 по последний)
first_stable=${deltas[1]}
last_stable=${deltas[$((RUNS-1))]}

diff=$(echo "$last_stable - $first_stable" | bc)

echo "Разница дельт (Прогон $RUNS минус Прогон 2): $diff КБ"
echo ""

# Логика итогового вывода
if (( $(echo "$diff < -10" | bc -l) )); then
    echo "РЕЗУЛЬТАТ: Потребление падает со временем. Система стабильна."
elif (( $(echo "$diff > 10" | bc -l) )); then
    echo "РЕЗУЛЬТАТ: ВНИМАНИЕ! Функция требует больше памяти от прогона к прогону."
else
    echo "РЕЗУЛЬТАТ: Потребление стабильно. Утечек нет."
fi

echo "======================================================================"
