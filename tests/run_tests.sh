#!/bin/bash
# SPDX-License-Identifier: GPL-3.0

# 1. Автоматически определяем корневую папку проекта
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Если скрипт лежит в tests/, поднимаемся на уровень вверх
if [[ "$SCRIPT_DIR" == */tests ]]; then
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi

# 2. Активация виртуального окружения
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

RUNS=10
PAUSE=2
MAIN_SCRIPT="$PROJECT_ROOT/main.py"

# Проверка, что main.py существует
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

for i in $(seq 1 $RUNS); do
    output=$(python3 "$MAIN_SCRIPT" 2>&1)

    # Парсинг
    mem_before=$(echo "$output" | grep "Используемая память до теста" | grep -oE '[0-9]+' | tail -1)
    mem_after=$(echo "$output" | grep "Используемая память после теста" | grep -oE '[0-9]+' | tail -1)
    delta=$(echo "$output" | grep "Результат:" | grep -oE '[0-9]+' | tail -1)
    speed=$(echo "$output" | grep "Скорость обработки" | grep -oE '[0-9]+' | tail -1)

    if echo "$output" | grep -q "уменьшилось"; then
        delta="-$delta"
    fi

    printf "%-5s | %-10s | %-10s | %-10s | %-12s\n" \
        "$i" "${mem_before:-N/A}" "${mem_after:-N/A}" "+${delta:-N/A}" "${speed:-N/A} п/с"

    deltas+=("${delta:-0}")

    if [ $i -lt $RUNS ]; then
        sleep $PAUSE
    fi
done

echo "======================================================================"
echo "АНАЛИЗ ТРЕНДА"
echo "======================================================================"

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
    echo "Средняя дельта за прогон: $avg КБ"
fi

first=${deltas[0]}
last=${deltas[$((RUNS-1))]}

echo "Дельта первого прогона:  +$first КБ"
echo "Дельта последнего прогона: +$last КБ"
echo ""

if [ -n "$first" ] && [ -n "$last" ]; then
    diff=$(echo "$last - $first" | bc)
    if (( $(echo "$diff < -50" | bc -l) )); then
        echo "РЕЗУЛЬТАТ: Дельта УМЕНЬШАЕТСЯ -> это прогрев аллокатора (НЕТ утечки)"
    elif (( $(echo "$diff > 50" | bc -l) )); then
        echo "РЕЗУЛЬТАТ: Дельта РАСТЁТ -> возможна утечка памяти"
    else
        echo "РЕЗУЛЬТАТ: Дельта СТАБИЛЬНА -> возможна линейная утечка"
    fi
fi

echo "======================================================================"