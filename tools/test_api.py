#!/usr/bin/env python3
"""
Test script to verify OpenRouter API connection
This script tests if your API key is working correctly.
"""

import requests
import json
import os

def test_api_connection():
    """Test the OpenRouter API connection"""
    print("🔍 Testing OpenRouter API connection...")
    
    try:
        # Get API key from environment
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("❌ No API key found in environment variables")
            return False
        
        print(f"✅ API key loaded: {api_key[:20]}...")
        
        # Test API connection with a simple request
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aoe2scenario-generator.com",
            "X-Title": "AoE2 Scenario Generator"
        }
        
        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello! Please respond with 'API connection successful' if you can read this."
                }
            ],
            "max_tokens": 50
        }
        
        print("🔄 Testing connection to anthropic/claude-3.5-sonnet...")
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            message = result["choices"][0]["message"]["content"]
            print(f"✅ API connection successful!")
            print(f"📝 Response: {message}")
            return True
        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(f"📝 Error: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return False
    except KeyError as e:
        print(f"❌ Unexpected response format: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_scenario_generation():
    """Test a simple scenario generation"""
    print("\n🔍 Testing scenario generation...")
    
    try:
        from generator import ScenarioGenerator, ScenarioConfig
        
        # Get API key
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("❌ No API key found")
            return False
        
        # Initialize generator
        generator = ScenarioGenerator(api_key)
        
        # Create a simple test config
        test_config = ScenarioConfig(
            title="Test Scenario",
            description="A simple test scenario to verify API functionality",
            scenario_type="battle",
            difficulty="easy",
            map_size=80,
            players=2,
            output_path="test_scenario.aoe2scenario"
        )
        
        print("🔄 Generating test scenario...")
        
        # Generate scenario code
        generated_code = generator.generate_scenario(test_config)
        
        if generated_code:
            print("✅ Scenario code generated successfully!")
            print(f"📝 Code length: {len(generated_code)} characters")
            
            # Validate the code
            if generator.validate_scenario_code(generated_code):
                print("✅ Generated code passed validation")
                return True
            else:
                print("⚠️  Generated code failed validation")
                return False
        else:
            print("❌ No scenario code generated")
            return False
            
    except Exception as e:
        print(f"❌ Scenario generation test failed: {e}")
        return False

def main():
    """Run API tests"""
    print("🚀 OpenRouter API Connection Test")
    print("=" * 50)
    
    # Test 1: Basic API connection
    api_test = test_api_connection()
    
    # Test 2: Scenario generation (only if API test passed)
    scenario_test = False
    if api_test:
        scenario_test = test_scenario_generation()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"  API Connection: {'✅ PASSED' if api_test else '❌ FAILED'}")
    print(f"  Scenario Generation: {'✅ PASSED' if scenario_test else '❌ FAILED'}")
    
    if api_test and scenario_test:
        print("\n🎉 All tests passed! Your API key is working correctly.")
        print("📝 You can now run:")
        print("   python create_scenario.py")
        print("   python examples/example_usage.py")
    elif api_test:
        print("\n⚠️  API connection works, but scenario generation failed.")
        print("📝 Check the error messages above for details.")
    else:
        print("\n❌ API connection failed. Please check your API key.")
        print("📝 Make sure your API key is set as environment variable")
    
    return api_test and scenario_test

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 