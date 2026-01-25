import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Space, List, Card, Typography, Tag } from 'antd';
import './ChatComps.css';

const { Text } = Typography;


function OutputDialog(props) {
  const chatHistory = props.chatHistory;
  const messagesEndRef = useRef(null);

  // tool function, scroll to the ref (end of message)
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Scroll if chat updated.
  useEffect(() => {
    scrollToBottom();
  }, [chatHistory]);


  const getStatusTag = (status, content) => {
    if (status === 'processing') {
      return <Tag color="orange">Processing...</Tag>;
    } else if (status === 'success') {
      return <Tag color="green">{content.startsWith('Case') ? content.split(' ')[0] + ' finish analysis' : 'Done'}</Tag>;
    } else if (status === 'error') {
      return <Tag color="red">{content.includes('Case') ? content.split(' ')[0] + ' unable to analyze' : 'Error'}</Tag>;
    }
    return null;
  };

  return (
      <div className="chat-container">
        <List
          dataSource={chatHistory}
          renderItem={item => (
            <List.Item className={`message-item  $ {item.type}`}>
              <Card 
                size="small" 
                className={`message-card  $ {item.type}`}
                title={
                  <Space>
                    <Text strong>{item.type === 'user' ? 'You' : 'Analyzer'}</Text>
                    {item.type === 'ai' && getStatusTag(item.status, item.content)}
                  </Space>
                }
              >
                <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>
              </Card>
            </List.Item>
          )}
        />
        <div ref={messagesEndRef} />
      </div>
  );
}

export default OutputDialog;