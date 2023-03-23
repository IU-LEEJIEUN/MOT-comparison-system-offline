max_val = None

with open('uav0000099_02109_v.txt', 'r') as f:
    for line in f:
        parts = line.split(',')
        first_val = int(parts[0])
        if max_val is None or first_val > max_val:
            max_val = first_val

print(f'The maximum first value is: {max_val}')
