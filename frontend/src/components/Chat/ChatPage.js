import React, { useState, useRef, useEffect } from 'react';
import { InputForm } from './InputForm';
import { OutputDialog } from './OutputDialog';
import './ChatComps.css';

export default function ChatPage(){
  const [targetURL, setTargetURL] = useState('');
  const [inputPrompt, setInputPrompt] = useState('');
  const [chatHistory, setChatHistory] = useState([]);

  const handleSend = async () => {
    if (!inputPrompt.trim()) return; // do nothing if no input

    const userMessageId = Date.now(); // timestamp as message ID
    const userMessage = {
      id: userMessageId,
      type: 'user',
      content: inputPrompt,
    };

    // Update user message to history
    setChatHistory(prev => [...prev, userMessage]);

    // Set initial message
    const aiMessageId = Date.now() + 1;
    const initialAiMessage = {
      id: aiMessageId,
      type: 'ai',
      content: 'Submitting...',
      status: 'processing',
    };
    setChatHistory(prev => [...prev, initialAiMessage]);

    // Callback function to update new message content 
    const updateAIMessage = (newContent, newStatus) => {
      setChatHistory(prev =>
        prev.map(msg => {
          if (msg.id === aiMessageId && msg.type === 'ai') {
            return {
              ...msg,
              content: newContent,
              status: newStatus || msg.status, // should consider no update
            };
          }
          return msg;
        })
      );
    };

    try {
      const response = await fetch('/test-webpage', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          //  If verification is required, add the corresponding header:
          // 'Authorization': `Bearer  $ {token}`,
        },
        body: JSON.stringify({ url: targetURL, prompt: inputPrompt }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! Status:  $ {response.status}`);
      }

      // Get the ReadableStream of response body
      const reader = response.body.getReader();
      // Decoding the text
      const decoder = new TextDecoder("utf-8");
      
      let accumulatedContent = ''; // Will accumulate event messages
      let buffer = ''; // Buffer for incomplete lines
      updateAIMessage('Processing started...', 'processing'); // Update UI

      while (true) {
        // Read a chunk of data (async)
        const { done, value } = await reader.read();

        if (done) {
          // Process any remaining buffer
          if (buffer.trim()) {
            try {
              const event = JSON.parse(buffer);
              if (event.type === 'completed') {
                accumulatedContent += '\n✓ Analysis completed successfully!';
              }
            } catch (e) {
              // Ignore parsing errors on final buffer
            }
          }
          console.log("Stream complete!");
          updateAIMessage(accumulatedContent || 'Processing completed', 'success');
          break;
        }

        // Decode the chunk of data
        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        // Process complete lines (JSON objects ending with \n)
        const lines = buffer.split('\n');
        buffer = lines[lines.length - 1]; // Keep incomplete line in buffer

        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (!line) continue;

          try {
            const event = JSON.parse(line);
            
            if (event.type === 'started') {
              accumulatedContent += `Analyzing: ${event.data.url}\n`;
              if (event.data.prompt) {
                accumulatedContent += `Prompt: ${event.data.prompt}\n`;
              }
            } else if (event.type === 'error') {
              accumulatedContent += `\n❌ Error: ${event.data.message}\n`;
            } else if (event.type === 'completed') {
              accumulatedContent += '\n✓ Analysis completed!\n';
              // Include the result data if available
              if (event.data) {
                accumulatedContent += `\nResults:\n${JSON.stringify(event.data, null, 2)}`;
              }
            } else {
              // Handle other event types
              accumulatedContent += `📊 ${event.type}: ${JSON.stringify(event.data)}\n`;
            }
          } catch (e) {
            console.error('Failed to parse event:', line, e);
          }
        }

        // Update UI in real-time
        updateAIMessage(accumulatedContent || 'Processing...', 'processing');
      }

      reader.releaseLock(); // Release lock

    } catch (error) {
      updateAIMessage(`Error in communication to service: ${error.message}`, 'error');
    }
  };

    return (
        <div className="app-container">
            {/* Target URL and prompt input */}
            <InputForm
                updateURL={setTargetURL}
                updatePrompt={setInputPrompt}
                onSubmit={handleSend}
                promptValue={inputPrompt}
                urlValue={targetURL}
            />
            {/* Chat history */}
            <OutputDialog
                chatHistory={chatHistory}
            />
        </div>
    )
}

