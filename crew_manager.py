or ``` markers
        lines = text.split('\n')
        cleaned_lines = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith('