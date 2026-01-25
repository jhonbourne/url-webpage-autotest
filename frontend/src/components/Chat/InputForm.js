import { Input, Button, Space, List, Card, Typography, Tag } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import './ChatComps.css';

const { TextArea } = Input;

function InputForm(props) {
    const urlPrompt = 'The URL of the webpage to test'
    const showSize = urlPrompt.length


    return (
      <div className="input-container">
        <Space.Compact style={{ width: '100%' }}>
          <TextArea 
            value={props.urlValue}
            onChange={(e) => props.updateURL(e.target.value)}
            placeholder="Please input the URL for test..."
            autoSize={{ minRows: 1, maxRows: 3 }}
            style={{ resize: 'none' }} 
          />
          <TextArea
            value={props.promptValue}
            onChange={(e) => props.updatePrompt(e.target.value)}
            placeholder="Please input your prompt of test cases..."
            autoSize={{ minRows: 1, maxRows: 6 }}
            style={{ resize: 'none' }} // prevent manual resizing
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={props.onSubmit}
            disabled={!props.promptValue.trim() | !props.urlValue.trim()} // Could not submit if missing input
          >
            Submit
          </Button>
        </Space.Compact>
        <form action={props.onQuerySubmit}>
            URL: <input type="text" name={props.urlName} 
                placeholder={urlPrompt} size={showSize} />
            <br />
            Prompt of test cases: <input type="text" name={props.promptName}
                size={showSize} />
            <br />
            <button type='submit'>Analyze the test cases</button>
        </form>
      </div>
    );
}

export default InputForm