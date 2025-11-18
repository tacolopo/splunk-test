# 🚀 START HERE - Testing Guide

## ✅ Repository Created!

**GitHub Repository**: https://github.com/tacolopo/splunk-test

Your code is now available at the link above. You can access it from any AWS instance or machine.

---

## 📋 Quick Start (30 minutes, $0)

### 🖥️ Testing from Your Local Machine? ⭐ START HERE

**📖 LOCAL_MACHINE_GUIDE.md** - Complete guide for running everything from your laptop

https://github.com/tacolopo/splunk-test/blob/master/LOCAL_MACHINE_GUIDE.md

This guide clearly marks:
- 💻 **Commands to run on YOUR LOCAL MACHINE**
- 🌐 **Actions to do in AWS Console (browser)**
- ✅ No confusion about where things run

**Perfect if:**
- You have Docker Desktop on your laptop
- You want to test everything locally first
- You already cloned the repo

---

### ☁️ Testing from AWS EC2/Cloud9?

**📖 AWS_SETUP.md** - Guide for setting up AWS resources first

https://github.com/tacolopo/splunk-test/blob/master/AWS_SETUP.md

Use this if you need to create an EC2 instance or Cloud9 environment first.

---

### 🚀 Quick Commands (If Using Local Machine)

```bash
# You're already in the repo, so just:
cd /home/user/Documents/Splunk\ to\ AWS\ Project

# Install dependencies
pip install -r requirements.txt

# Create AWS resources
python create_dynamodb_table.py --region us-east-1
aws s3 mb s3://splunk-obs-$(date +%s) --region us-east-1

# Start Docker Splunk
docker run -d -p 8000:8000 -p 8089:8089 \
  -e SPLUNK_PASSWORD='Changeme123!' --name splunk splunk/splunk:latest

# Then follow LOCAL_MACHINE_GUIDE.md for complete steps
```

---

## 🎯 Three Ways to Test

### Option 1: Quick Mock Test (5 min, no AWS/Splunk)

```bash
git clone https://github.com/tacolopo/splunk-test.git
cd splunk-test
pip install -r requirements.txt
python test_mock_export.py
```

### Option 2: AWS Free Tier Test (15 min, no Splunk)

```bash
git clone https://github.com/tacolopo/splunk-test.git
cd splunk-test
pip install -r requirements.txt
python create_dynamodb_table.py --region us-east-1
python test_with_sample_data.py
python test_ip_address.py
```

### Option 3: Full Integration Test (30 min) ⭐ RECOMMENDED

**Follow `QUICKSTART.md` for complete step-by-step instructions**

---

## 📚 Documentation

All documentation is in the repository:

| File | Description |
|------|-------------|
| **`AWS_SETUP.md`** | **AWS resources setup from scratch** ⭐ START HERE |
| **`QUICKSTART.md`** | **Complete step-by-step testing guide** ⭐ |
| `CHEATSHEET.md` | Quick reference commands |
| `README.md` | Full project documentation |
| `TESTING.md` | All testing scenarios |
| `ARCHITECTURE.md` | System architecture details |
| `SECURITY.md` | Security best practices |
| `DEPLOYMENT.md` | Production deployment guide |

---

## 🔧 What You Need

Before starting:
- ✅ AWS account (Free Tier eligible)
- ✅ Docker installed
- ✅ AWS CLI configured (`aws configure`)
- ✅ Python 3.7+ installed

---

## 💡 Key Commands

```bash
# Clone repo
git clone https://github.com/tacolopo/splunk-test.git
cd splunk-test

# Install dependencies
pip install -r requirements.txt

# Start Splunk Docker
docker run -d -p 8000:8000 -p 8089:8089 \
  -e SPLUNK_PASSWORD='Changeme123!' \
  --name splunk splunk/splunk:latest

# Create AWS resources
python create_dynamodb_table.py --region us-east-1

# Run test
./test_full_pipeline.sh
```

---

## 🎓 What This Solution Does

1. **Splunk**: Aggregates security observables (IPs, emails, hashes) hourly
2. **Lambda**: Automatically exports data every hour
3. **DynamoDB**: Stores recent observables (90 days) for fast lookups
4. **S3**: Archives all historical data forever

**Use Case**: "When was IP 1.2.3.4 first seen? How many times? When was it last seen?"

---

## 📊 Repository Contents

```
splunk-test/
├── QUICKSTART.md              ⭐ START HERE for testing
├── CHEATSHEET.md              Quick command reference
├── README.md                  Full documentation
├── export_to_aws.py           Main export script
├── lambda_function.py         Lambda handler
├── requirements.txt           Python dependencies
├── terraform/                 Infrastructure as code
├── splunk_queries/            SPL queries
├── test_*.py                  Test scripts
└── Documentation files        Security, architecture, etc.
```

---

## ✨ Next Steps

1. **Read `QUICKSTART.md`** - Complete step-by-step guide
2. **Clone the repo** on your AWS instance
3. **Follow the guide** - all commands provided
4. **Test with sample data** - Docker Splunk + AWS Free Tier
5. **Deploy to production** - Use Terraform for automation

---

## 🆘 Need Help?

- **Full Testing Guide**: See `TESTING.md`
- **Troubleshooting**: See `QUICKSTART.md` Step 10
- **Architecture**: See `ARCHITECTURE.md`
- **GitHub Issues**: https://github.com/tacolopo/splunk-test/issues

---

## 📦 What's Included

✅ Complete working code  
✅ Terraform for AWS deployment  
✅ Docker Splunk setup instructions  
✅ Sample data generation  
✅ Test scripts  
✅ Comprehensive documentation  
✅ Security best practices  
✅ Performance optimization guide  
✅ Cost estimates  

**Total Cost**: $0 during testing (AWS Free Tier)  
**Production Cost**: ~$100-200/month

---

## 🎉 You're Ready!

The code is on GitHub and ready to test. When you log into AWS:

1. Clone: `git clone https://github.com/tacolopo/splunk-test.git`
2. Open: `QUICKSTART.md`
3. Follow the step-by-step instructions
4. Test the solution!

**GitHub Repository**: https://github.com/tacolopo/splunk-test

Good luck! 🚀

