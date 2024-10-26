#!/bin/bash

# Variables
TOMCAT_VERSION=10.1.31
INSTALL_DIR=$HOME/tomcat   # Install in the user's home directory
SERVICE_NAME=tomcat

# Update packages
echo "Updating packages..."
sudo apt update && sudo apt upgrade -y

# Install Java
echo "Installing Java 21..."
sudo apt install -y openjdk-21-jdk

# Download Tomcat 10.1.31
echo "Downloading Tomcat 10.1.31..."
wget https://downloads.apache.org/tomcat/tomcat-10/v$TOMCAT_VERSION/bin/apache-tomcat-$TOMCAT_VERSION.tar.gz -P /tmp

# Install Tomcat
echo "Installing Tomcat..."
mkdir -p $INSTALL_DIR
tar -xf /tmp/apache-tomcat-$TOMCAT_VERSION.tar.gz -C $INSTALL_DIR
ln -s $INSTALL_DIR/apache-tomcat-$TOMCAT_VERSION $INSTALL_DIR/latest

# Setup permissions
echo "Setting permissions..."
chmod +x $INSTALL_DIR/latest/bin/*.sh

# Create systemd service file
echo "Creating systemd service file..."
cat <<EOF | sudo tee /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Apache Tomcat Web Application Container
After=network.target

[Service]
Type=forking

User=$USER
Group=$USER

Environment=JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
Environment=CATALINA_PID=$INSTALL_DIR/latest/temp/tomcat.pid
Environment=CATALINA_HOME=$INSTALL_DIR/latest
Environment=CATALINA_BASE=$INSTALL_DIR/latest
Environment='CATALINA_OPTS=-Xms512M -Xmx1024M -server -XX:+UseParallelGC'
Environment='JAVA_OPTS=-Djava.awt.headless=true -Djava.security.egd=file:/dev/./urandom'

ExecStart=$INSTALL_DIR/latest/bin/startup.sh
ExecStop=$INSTALL_DIR/latest/bin/shutdown.sh

Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start Tomcat
echo "Starting Tomcat..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

# Install AWS CodeDeploy Agent
echo "Installing AWS CodeDeploy agent..."
sudo apt update
sudo apt install -y ruby-full wget

# Download and install the CodeDeploy agent
cd /home/$USER
wget https://aws-codedeploy-ap-southeast-1.s3.ap-southeast-1.amazonaws.com/latest/install
sudo chmod +x ./install
sudo ./install auto

# Start CodeDeploy agent
sudo systemctl start codedeploy-agent
sudo systemctl enable codedeploy-agent
