#!/bin/bash
cd "$(dirname "$0")"
export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"
# java -Dserver.port=2333 -jar lavalink/Lavalink.jar
java -Djava.util.logging.config.file=logging.properties -Dserver.port=2333 -jar lavalink/Lavalink.jar
