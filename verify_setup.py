#!/usr/bin/env python3
"""
Setup Verification Script - Business Analytics Agent
====================================================
Run this script to verify all components are properly configured.
"""

import os
import sys

def check_dependencies():
    """Verify all required dependencies are installed."""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        "streamlit",
        "anthropic",
        "pandas",
        "plotly",
        "psycopg2",
        "python-dotenv",
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} - MISSING")
            missing.append(package)
    
    return len(missing) == 0, missing


def check_env_config():
    """Verify environment configuration."""
    print("\n🔍 Checking environment configuration...")
    
    required_env = [
        "ANTHROPIC_API_KEY",
    ]
    
    optional_env = [
        "ANTHROPIC_MODEL",
        "DATABASE_URL",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
    ]
    
    missing_required = []
    for var in required_env:
        if os.getenv(var):
            print(f"  ✅ {var}")
        else:
            print(f"  ❌ {var} - MISSING (REQUIRED)")
            missing_required.append(var)
    
    print("\n  Optional variables:")
    for var in optional_env:
        if os.getenv(var):
            print(f"    ✅ {var}")
        else:
            print(f"    ⚠️  {var} - not set")
    
    return len(missing_required) == 0, missing_required


def check_anthropic_api():
    """Test Anthropic API connection."""
    print("\n🔍 Testing Anthropic API connection...")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ❌ ANTHROPIC_API_KEY not set")
        return False
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        
        # Test basic API call
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Say 'Hello' only"}
            ]
        )
        
        print(f"  ✅ API connection successful")
        print(f"     Response: {message.content[0].text}")
        return True
    
    except Exception as e:
        print(f"  ❌ API test failed: {str(e)}")
        return False


def check_database():
    """Test database connection."""
    print("\n🔍 Testing database connection...")
    
    try:
        from src.database.connection import get_connection
        
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
        conn.close()
        
        print("  ✅ Database connection successful")
        return True
    
    except Exception as e:
        print(f"  ❌ Database connection failed: {str(e)}")
        print("     Make sure database is running and configured in config/settings.py")
        return False


def check_visualization_module():
    """Verify visualization module imports."""
    print("\n🔍 Checking visualization module...")
    
    try:
        from src.ai.business_analytics import (
            create_horizontal_bar_chart,
            create_line_chart,
            create_pie_chart,
            render_business_report,
        )
        print("  ✅ business_analytics module loaded")
        return True
    except Exception as e:
        print(f"  ❌ Visualization module error: {str(e)}")
        return False


def check_chatbot_module():
    """Verify chatbot module imports."""
    print("\n🔍 Checking chatbot module...")
    
    try:
        from src.ai.custom_chatbot import render_custom_chatbot
        print("  ✅ custom_chatbot module loaded")
        return True
    except Exception as e:
        print(f"  ❌ Chatbot module error: {str(e)}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("  Business Analytics Agent - Setup Verification")
    print("=" * 60)
    
    results = {}
    
    # Run checks
    results["dependencies"] = check_dependencies()[0]
    results["env_config"] = check_env_config()[0]
    results["visualization"] = check_visualization_module()
    results["chatbot"] = check_chatbot_module()
    
    # Optional checks (don't fail on these)
    results["anthropic_api"] = check_anthropic_api()
    results["database"] = check_database()
    
    # Summary
    print("\n" + "=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)
    
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {check.replace('_', ' ').title()}")
    
    print("\n" + "=" * 60)
    
    # Overall result
    critical_checks = [
        results.get("dependencies", False),
        results.get("env_config", False),
        results.get("visualization", False),
        results.get("chatbot", False),
    ]
    
    if all(critical_checks):
        print("\n✅ All critical checks passed!")
        print("\nTo run the dashboard:")
        print("  streamlit run streamlit_app.py")
        print("\nTo run the business report demo:")
        print("  streamlit run src/ai/business_report_demo.py")
        print("\nNext steps:")
        print("  1. Set ANTHROPIC_API_KEY environment variable")
        print("  2. Configure database connection (if using remote DB)")
        print("  3. Run the Streamlit app")
        return 0
    else:
        print("\n❌ Some critical checks failed!")
        print("\nPlease fix the errors above and try again.")
        print("\nFor help, see BUSINESS_ANALYTICS_GUIDE.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
