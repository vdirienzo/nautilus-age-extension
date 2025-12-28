#!/bin/bash
# age-wrapper.sh
# Wrapper for age that uses zenity to request passwords
# This solves the issue that age reads from /dev/tty

MODE=""
OUTPUT_FILE=""
INPUT_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--passphrase)
            MODE="encrypt"
            shift
            ;;
        -d|--decrypt)
            MODE="decrypt"
            shift
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -i|--input)
            INPUT_FILE="$2"
            shift 2
            ;;
        *)
            if [[ -z "$INPUT_FILE" ]]; then
                INPUT_FILE="$1"
            fi
            shift
            ;;
    esac
done

if [[ "$MODE" == "encrypt" ]]; then
    # Encryption mode
    PASSWORD=$(zenity --password --title="age Encryption" --text="Enter encryption password:")
    if [[ -z "$PASSWORD" ]]; then
        exit 1
    fi

    PASSWORD_CONFIRM=$(zenity --password --title="Confirm Password" --text="Re-enter password:")
    if [[ "$PASSWORD" != "$PASSWORD_CONFIRM" ]]; then
        zenity --error --text="Passwords don't match!"
        exit 1
    fi

    # Encrypt
    if [[ -n "$INPUT_FILE" && -n "$OUTPUT_FILE" ]]; then
        echo -e "$PASSWORD\n$PASSWORD" | age -p < "$INPUT_FILE" > "$OUTPUT_FILE" 2>&1
    elif [[ -n "$OUTPUT_FILE" ]]; then
        echo -e "$PASSWORD\n$PASSWORD" | age -p > "$OUTPUT_FILE" 2>&1
    elif [[ -n "$INPUT_FILE" ]]; then
        echo -e "$PASSWORD\n$PASSWORD" | age -p < "$INPUT_FILE" 2>&1
    else
        echo -e "$PASSWORD\n$PASSWORD" | age -p 2>&1
    fi

elif [[ "$MODE" == "decrypt" ]]; then
    # Decryption mode
    PASSWORD=$(zenity --password --title="age Decryption" --text="Enter decryption password:")
    if [[ -z "$PASSWORD" ]]; then
        exit 1
    fi

    # Decrypt
    if [[ -n "$INPUT_FILE" && -n "$OUTPUT_FILE" ]]; then
        echo "$PASSWORD" | age -d < "$INPUT_FILE" > "$OUTPUT_FILE" 2>&1
    elif [[ -n "$OUTPUT_FILE" ]]; then
        echo "$PASSWORD" | age -d > "$OUTPUT_FILE" 2>&1
    elif [[ -n "$INPUT_FILE" ]]; then
        echo "$PASSWORD" | age -d < "$INPUT_FILE" 2>&1
    else
        echo "$PASSWORD" | age -d 2>&1
    fi
else
    echo "Error: Specify -p (encrypt) or -d (decrypt)"
    exit 1
fi

exit $?
